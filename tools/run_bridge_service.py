#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
import threading
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn

from droid_web_display.api import create_app
from droid_web_display.config import BridgeConfig
from droid_web_display.network_access import LAN_HTTPS, LOCAL_ONLY, FirewallManager, NetworkAccessError, NetworkConfigStore
from droid_web_display.runtime import require_websocket_backend


def _bridge_config(args: argparse.Namespace, network) -> BridgeConfig:
    if args.host:
        network = type(network)(mode=LOCAL_ONLY, bind_address=args.host, port=args.port or network.port)
    return BridgeConfig(
        repo_root=args.repo_root.resolve(),
        adb_executable=args.adb,
        bind_host=network.bind_address,
        bind_port=args.port or network.port,
        transfer_data_directory=args.data_directory.resolve() if args.data_directory else None,
        default_download_directory=args.download_directory.resolve() if args.download_directory else None,
        transfer_concurrency=args.transfer_concurrency,
        maximum_file_size=args.maximum_file_size,
        authentication_required=True,
        network_mode=network.mode,
        allowed_client_networks=network.allowed_networks,
        tls_enabled=network.mode == LAN_HTTPS,
        tls_certificate_path=Path(network.tls.certificate_path) if network.tls.certificate_path else None,
        tls_private_key_path=Path(network.tls.private_key_path) if network.tls.private_key_path else None,
        configured_hostname=network.hostname,
        network_config_file=args.network_config.resolve(),
    )


async def _serve_once(args: argparse.Namespace, network, websocket_backend: str, *, open_browser: bool) -> bool:
    config = _bridge_config(args, network)
    config.validate()
    restart_requested = False
    server_holder: dict[str, uvicorn.Server] = {}

    def request_restart() -> None:
        nonlocal restart_requested
        restart_requested = True
        server = server_holder.get("server")
        if server is not None:
            server.should_exit = True

    app = create_app(config=config)
    app.state.request_restart = request_restart
    uvicorn_config = uvicorn.Config(
        app,
        host=config.bind_host,
        port=config.bind_port,
        log_level="info",
        ssl_certfile=str(config.tls_certificate_path) if config.tls_enabled and config.tls_certificate_path else None,
        ssl_keyfile=str(config.tls_private_key_path) if config.tls_enabled and config.tls_private_key_path else None,
    )
    server = uvicorn.Server(uvicorn_config)
    server_holder["server"] = server
    scheme = "https" if config.tls_enabled else "http"
    display_host = config.configured_hostname or config.bind_host
    url = f"{scheme}://{display_host}:{config.bind_port}/"
    print(f"DroidWebDisplay: {url}")
    print(f"Network access mode: {config.network_mode}")
    print(f"WebSocket backend: {websocket_backend}")
    print(f"PC download folder: {config.resolved_default_download_directory}")
    print(f"Transfer concurrency: {config.transfer_concurrency}")
    print(f"Authentication store: {config.resolved_auth_data_file}")
    print(f"Network configuration: {config.resolved_network_config_file}")
    print("Trust authority: this PC bridge (not the Android phone)")
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    await server.serve()
    return restart_requested


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the DroidWebDisplay browser service")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--adb", help="ADB executable; defaults to bundled adb/ when present, otherwise PATH")
    parser.add_argument("--host", help="Emergency local bind override; normally loaded from network-access.json")
    parser.add_argument("--port", type=int)
    parser.add_argument("--network-config", type=Path)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--no-browser", action="store_true", help="Do not launch the browser even if a launcher requested it")
    parser.add_argument("--data-directory", type=Path, help="Persistent state directory (auth, network and transfer metadata)")
    parser.add_argument("--download-directory", type=Path)
    parser.add_argument("--transfer-concurrency", type=int, default=1)
    parser.add_argument("--maximum-file-size", type=int, default=2 * 1024 * 1024 * 1024)
    parser.add_argument("--pid-file", type=Path, help="Write the running service PID here and remove it on clean exit")
    args = parser.parse_args()
    args.repo_root = args.repo_root.resolve()
    if not args.adb:
        bundled = args.repo_root / "adb" / ("adb.exe" if os.name == "nt" else "adb")
        args.adb = str(bundled) if bundled.is_file() else "adb"
    if args.data_directory:
        args.data_directory = args.data_directory.resolve()
    default_state = args.data_directory or (args.repo_root / "data")
    args.network_config = (args.network_config or (default_state / "network-access.json")).resolve()

    try:
        websocket_backend = require_websocket_backend()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    pid_file = args.pid_file.resolve() if args.pid_file else None
    if pid_file:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = pid_file.with_suffix(pid_file.suffix + ".tmp")
        temporary.write_text(f"{os.getpid()}\n", encoding="ascii")
        temporary.replace(pid_file)

    store = NetworkConfigStore(args.network_config)
    open_browser = args.open_browser and not args.no_browser
    try:
        while True:
            try:
                network = store.load()
                network.validate(require_files=network.mode == LAN_HTTPS)
            except NetworkAccessError as exc:
                print(f"WARNING: LAN configuration failed validation: {exc}", file=sys.stderr)
                print("Falling back to local-only access at 127.0.0.1.", file=sys.stderr)
                network = store.reset_local_only(port=args.port or 8765)
            try:
                restart = asyncio.run(_serve_once(args, network, websocket_backend, open_browser=open_browser))
            except (OSError, SystemExit, ValueError) as exc:
                if network.mode == LAN_HTTPS:
                    print(f"ERROR: LAN listener failed: {exc}", file=sys.stderr)
                    FirewallManager().apply(network, remove=True)
                    store.reset_local_only(port=network.port)
                    print("Recovered to local-only mode. Restarting on 127.0.0.1.", file=sys.stderr)
                    open_browser = True
                    continue
                print(f"ERROR: service failed to start: {exc}", file=sys.stderr)
                return 3
            if not restart:
                return 0
            open_browser = False
            print("Network configuration changed; restarting DroidWebDisplay...")
    finally:
        if pid_file:
            try:
                if pid_file.read_text(encoding="ascii").strip() == str(os.getpid()):
                    pid_file.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
