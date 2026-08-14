#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from contextlib import suppress
import logging
import os
from pathlib import Path
import socket
import ssl
import sys
import threading
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import uvicorn

from droid_web_display import __version__
from droid_web_display.api import create_app
from droid_web_display.config import BridgeConfig
from droid_web_display.diagnostics import DiagnosticLoggingMiddleware, configure_server_logging
from droid_web_display.network_access import (
    LAN_HTTPS,
    LOCAL_ONLY,
    FirewallManager,
    NetworkAccessError,
    NetworkConfigStore,
)
from droid_web_display.runtime import require_websocket_backend


PRODUCT_TITLE_MARKER = "<title>DroidWebDisplay</title>"
WEB_UI_MARKER = "droidwebdisplay-native-single-drawer-v1"


class ExistingWebServiceError(RuntimeError):
    """Raised when the configured listener belongs to an older or unrelated service."""


class BridgeServiceRuntime:
    """Thread-safe lifecycle handle used by the desktop host to stop Uvicorn cleanly."""

    def __init__(self) -> None:
        self._shutdown = threading.Event()
        self._lock = threading.RLock()
        self._server: uvicorn.Server | None = None

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown.is_set()

    def attach(self, server: uvicorn.Server) -> None:
        with self._lock:
            self._server = server
            if self._shutdown.is_set():
                server.should_exit = True

    def detach(self, server: uvicorn.Server) -> None:
        with self._lock:
            if self._server is server:
                self._server = None

    def request_shutdown(self) -> None:
        self._shutdown.set()
        with self._lock:
            if self._server is not None:
                self._server.should_exit = True


def _probe_host(bind_host: str) -> str:
    if bind_host in {"0.0.0.0", ""}:
        return "127.0.0.1"
    if bind_host == "::":
        return "::1"
    return bind_host


def _port_is_listening(bind_host: str, port: int) -> bool:
    try:
        with socket.create_connection((_probe_host(bind_host), port), timeout=0.35):
            return True
    except OSError:
        return False


def _fetch_root_html(url: str) -> str | None:
    context = None
    if url.lower().startswith("https://"):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "DroidWebDisplay-runtime-probe/1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=0.8, context=context) as response:
            return response.read(512 * 1024).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _is_current_web_ui(html: str | None) -> bool:
    return bool(html and PRODUCT_TITLE_MARKER in html and WEB_UI_MARKER in html)


def _classify_existing_service(url: str, bind_host: str, port: int) -> str:
    if not _port_is_listening(bind_host, port):
        return "none"
    return "current" if _is_current_web_ui(_fetch_root_html(url)) else "other"


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


async def _serve_once(
    args: argparse.Namespace,
    network,
    websocket_backend: str,
    logger: logging.Logger,
    *,
    open_browser: bool,
    runtime: BridgeServiceRuntime | None = None,
) -> bool:
    config = _bridge_config(args, network)
    config.validate()
    scheme = "https" if config.tls_enabled else "http"
    display_host = config.configured_hostname or config.bind_host
    url = f"{scheme}://{display_host}:{config.bind_port}/"

    existing = _classify_existing_service(url, config.bind_host, config.bind_port)
    if existing == "current":
        logger.info(
            "DroidWebDisplay is already running at %s",
            url,
            extra={"event": "server.existing", "url": url, "network_mode": config.network_mode},
        )
        print(f"DroidWebDisplay is already running at {url}")
        print("Existing listener serves the current DroidWebDisplay web UI marker.")
        if open_browser:
            webbrowser.open(url)
        return False
    if existing == "other":
        logger.error(
            "Configured listener is already used by another service",
            extra={"event": "server.port_conflict", "url": url, "network_mode": config.network_mode},
        )
        raise ExistingWebServiceError(
            f"Port {config.bind_port} on {config.bind_host} is already in use by an older or unrelated "
            "web service. "
            "Stop that process (or choose another port) before starting this DroidWebDisplay checkout."
        )

    restart_requested = False
    server_holder: dict[str, uvicorn.Server] = {}

    def request_restart() -> None:
        nonlocal restart_requested
        restart_requested = True
        logger.info(
            "Server restart requested",
            extra={"event": "server.restart_requested", "restart_requested": True},
        )
        server = server_holder.get("server")
        if server is not None:
            server.should_exit = True

    fastapi_app = create_app(config=config)
    fastapi_app.state.request_restart = request_restart
    app = DiagnosticLoggingMiddleware(fastapi_app, logger=logger)
    uvicorn_config = uvicorn.Config(
        app,
        host=config.bind_host,
        port=config.bind_port,
        log_level=args.log_level.lower(),
        log_config=None,
        access_log=False,
        ssl_certfile=(
            str(config.tls_certificate_path)
            if config.tls_enabled and config.tls_certificate_path
            else None
        ),
        ssl_keyfile=(
            str(config.tls_private_key_path)
            if config.tls_enabled and config.tls_private_key_path
            else None
        ),
    )
    server = uvicorn.Server(uvicorn_config)
    server_holder["server"] = server
    if runtime is not None:
        runtime.attach(server)
    print(f"DroidWebDisplay: {url}")
    print(f"Web root: {config.repo_root / 'apps' / 'web-client' / 'dist'}")
    print(f"Web UI marker: {WEB_UI_MARKER}")
    print(f"Network access mode: {config.network_mode}")
    print(f"WebSocket backend: {websocket_backend}")
    print(f"PC download folder: {config.resolved_default_download_directory}")
    print(f"Transfer concurrency: {config.transfer_concurrency}")
    print(f"Authentication store: {config.resolved_auth_data_file}")
    print(f"Network configuration: {config.resolved_network_config_file}")
    print(f"Server diagnostics: {args.log_directory / 'server.log'}")
    print("Trust authority: this PC bridge (not the Android phone)")
    logger.info(
        "DroidWebDisplay server starting",
        extra={
            "event": "server.starting",
            "pid": os.getpid(),
            "version": __version__,
            "url": url,
            "network_mode": config.network_mode,
            "websocket_backend": websocket_backend,
            "log_file": str(args.log_directory / "server.log"),
        },
    )

    async def open_browser_after_start() -> None:
        while not server.started and not server.should_exit:
            await asyncio.sleep(0.05)
        if server.started and not server.should_exit:
            webbrowser.open(url)

    browser_task = asyncio.create_task(open_browser_after_start()) if open_browser else None
    try:
        await server.serve()
    finally:
        if browser_task is not None and not browser_task.done():
            browser_task.cancel()
            with suppress(asyncio.CancelledError):
                await browser_task
        if runtime is not None:
            runtime.detach(server)
        logger.info(
            "DroidWebDisplay server stopped",
            extra={
                "event": "server.stopped",
                "pid": os.getpid(),
                "url": url,
                "network_mode": config.network_mode,
                "restart_requested": restart_requested,
                "reason": "desktop-shutdown"
                if runtime is not None and runtime.shutdown_requested
                else ("configuration-restart" if restart_requested else "normal"),
            },
        )
    return restart_requested and not (runtime is not None and runtime.shutdown_requested)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the DroidWebDisplay browser service")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--adb", help="ADB executable; defaults to bundled adb/ when present, otherwise PATH")
    parser.add_argument(
        "--host",
        help="Emergency local bind override; normally loaded from network-access.json",
    )
    parser.add_argument("--port", type=int)
    parser.add_argument("--network-config", type=Path)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not launch the browser even if a launcher requested it",
    )
    parser.add_argument(
        "--data-directory",
        type=Path,
        help="Persistent state directory (auth, network and transfer metadata)",
    )
    parser.add_argument("--download-directory", type=Path)
    parser.add_argument("--transfer-concurrency", type=int, default=1)
    parser.add_argument("--maximum-file-size", type=int, default=2 * 1024 * 1024 * 1024)
    parser.add_argument(
        "--pid-file",
        type=Path,
        help="Write the running service PID here and remove it on clean exit",
    )
    parser.add_argument(
        "--log-directory",
        type=Path,
        help="Directory for rotating server.log JSONL diagnostics",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default=os.environ.get("DWD_LOG_LEVEL", "INFO").upper(),
        help="Server diagnostic verbosity (or set DWD_LOG_LEVEL)",
    )
    parser.add_argument(
        "--log-max-bytes",
        type=int,
        default=5 * 1024 * 1024,
        help="Rotate server.log after this many bytes",
    )
    parser.add_argument(
        "--log-backups",
        type=int,
        default=5,
        help="Number of rotated server.log generations to retain",
    )
    return parser


def main(argv: list[str] | None = None, runtime: BridgeServiceRuntime | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.repo_root = args.repo_root.resolve()
    if not args.adb:
        bundled = args.repo_root / "adb" / ("adb.exe" if os.name == "nt" else "adb")
        args.adb = str(bundled) if bundled.is_file() else "adb"
    if args.data_directory:
        args.data_directory = args.data_directory.resolve()
    default_state = args.data_directory or (args.repo_root / "data")
    args.network_config = (args.network_config or (default_state / "network-access.json")).resolve()
    args.log_directory = (args.log_directory or (default_state / "logs")).resolve()

    try:
        logger, log_path = configure_server_logging(
            args.log_directory,
            level=args.log_level,
            maximum_bytes=args.log_max_bytes,
            backup_count=args.log_backups,
        )
    except (OSError, ValueError) as exc:
        print(f"WARNING: server diagnostic logging could not be initialized: {exc}", file=sys.stderr)
        logger = logging.getLogger("droid_web_display.server")
        log_path = args.log_directory / "server.log"

    logger.info(
        "DroidWebDisplay service process initialized",
        extra={
            "event": "process.start",
            "pid": os.getpid(),
            "version": __version__,
            "log_file": str(log_path),
        },
    )

    try:
        websocket_backend = require_websocket_backend()
    except RuntimeError as exc:
        logger.error(
            "WebSocket backend is unavailable: %s",
            exc,
            extra={"event": "server.dependency_error", "error_code": "websocket_backend"},
        )
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
            if runtime is not None and runtime.shutdown_requested:
                logger.info(
                    "Shutdown requested before listener start",
                    extra={"event": "server.shutdown_requested", "reason": "desktop-host"},
                )
                return 0
            try:
                network = store.load()
                network.validate(require_files=network.mode == LAN_HTTPS)
            except NetworkAccessError as exc:
                logger.warning(
                    "LAN configuration failed validation; falling back to local-only access: %s",
                    exc,
                    extra={
                        "event": "network.validation_failed",
                        "error_code": getattr(exc, "code", "network_error"),
                        "network_mode": LAN_HTTPS,
                    },
                )
                print(f"WARNING: LAN configuration failed validation: {exc}", file=sys.stderr)
                print("Falling back to local-only access at 127.0.0.1.", file=sys.stderr)
                network = store.reset_local_only(port=args.port or 8765)
            try:
                restart = asyncio.run(
                    _serve_once(
                        args,
                        network,
                        websocket_backend,
                        logger,
                        open_browser=open_browser,
                        runtime=runtime,
                    )
                )
            except ExistingWebServiceError as exc:
                logger.error(
                    "Service start blocked by an existing listener: %s",
                    exc,
                    extra={"event": "server.start_failed", "error_code": "port_in_use"},
                )
                print(f"ERROR: {exc}", file=sys.stderr)
                print(
                    "The browser was not opened, so an older page cannot be mistaken for this checkout.",
                    file=sys.stderr,
                )
                return 4
            except (OSError, SystemExit, ValueError) as exc:
                if network.mode == LAN_HTTPS:
                    logger.exception(
                        "LAN listener failed; recovering to local-only mode",
                        extra={
                            "event": "server.listener_failed",
                            "error_code": type(exc).__name__,
                            "network_mode": network.mode,
                        },
                    )
                    print(f"ERROR: LAN listener failed: {exc}", file=sys.stderr)
                    FirewallManager().apply(network, remove=True)
                    store.reset_local_only(port=network.port)
                    print("Recovered to local-only mode. Restarting on 127.0.0.1.", file=sys.stderr)
                    open_browser = True
                    continue
                logger.exception(
                    "Service failed to start",
                    extra={"event": "server.start_failed", "error_code": type(exc).__name__},
                )
                print(f"ERROR: service failed to start: {exc}", file=sys.stderr)
                return 3
            if runtime is not None and runtime.shutdown_requested:
                return 0
            if not restart:
                return 0
            open_browser = False
            logger.info(
                "Network configuration changed; restarting DroidWebDisplay",
                extra={"event": "server.restarting", "reason": "network-configuration"},
            )
            print("Network configuration changed; restarting DroidWebDisplay...")
    finally:
        logger.info(
            "DroidWebDisplay service process exiting",
            extra={"event": "process.stop", "pid": os.getpid()},
        )
        if pid_file:
            try:
                if pid_file.read_text(encoding="ascii").strip() == str(os.getpid()):
                    pid_file.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
