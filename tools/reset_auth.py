#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import ssl
import urllib.error
import urllib.request

from droid_web_display.auth import AuthService
from droid_web_display.config import BridgeConfig
from droid_web_display.network_access import (
    FirewallManager,
    LAN_HTTPS,
    NetworkAccessConfig,
    NetworkConfigStore,
)


def _stored_network_config(path: Path) -> NetworkAccessConfig:
    if not path.is_file():
        return NetworkAccessConfig()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return NetworkAccessConfig.from_dict(value)
    except Exception:
        pass
    return NetworkAccessConfig()


def _probe_auth_status(url: str) -> bool:
    context = None
    if url.lower().startswith("https://"):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/v1/auth/status",
        headers={"User-Agent": "DroidWebDisplay-reset-auth/1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=0.8, context=context) as response:
            payload = json.loads(response.read(64 * 1024).decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
        return False
    return isinstance(payload, dict) and payload.get("trustModel") == "pc-local" and "configured" in payload


def _service_running(network: NetworkAccessConfig) -> bool:
    candidates = {f"http://127.0.0.1:{network.port}"}
    if network.mode == LAN_HTTPS:
        candidates.add(f"https://{network.bind_address}:{network.port}")
    return any(_probe_auth_status(url) for url in candidates)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the PC-local DroidWebDisplay PIN and trusted sessions")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--yes", action="store_true", help="Confirm destructive reset")
    args = parser.parse_args()
    if not args.yes:
        print("Refusing to reset authentication without --yes")
        return 2

    config = BridgeConfig(repo_root=args.repo_root.resolve())
    network = _stored_network_config(config.resolved_network_config_file)
    if _service_running(network):
        print("Refusing to reset authentication while DroidWebDisplay is running.")
        print("Stop the service first, then run this command again.")
        return 3

    service = AuthService(config.resolved_auth_data_file)
    service.reset()

    if network.mode == LAN_HTTPS and network.firewall.manage_rule:
        result = FirewallManager().apply(network, remove=True)
        if not result.get("applied", False) and result.get("reason") not in {None, "Windows-only"}:
            print(f"WARNING: firewall rule removal was not confirmed: {result.get('reason')}")

    NetworkConfigStore(config.resolved_network_config_file).reset_local_only(port=network.port)
    print(f"Reset authentication store: {config.resolved_auth_data_file}")
    print(f"Reset network access to local-only: {config.resolved_network_config_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
