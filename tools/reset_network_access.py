#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gpt_bridge.auth import AuthService
from gpt_bridge.network_access import FirewallManager, LAN_HTTPS, NetworkAccessError, NetworkConfigStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover Gpt-Bridge to local-only network access")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--local-only", action="store_true", required=True)
    parser.add_argument("--port", type=int)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    store = NetworkConfigStore(root / "data" / "network-access.json")
    try:
        previous = store.load()
    except NetworkAccessError:
        previous = None
    if previous and previous.mode == LAN_HTTPS and previous.firewall.manage_rule:
        result = FirewallManager().apply(previous, remove=True)
        if not result.get("applied"):
            print("Firewall rule could not be removed automatically.")
            print("Manual command:", "powershell.exe", *result.get("command", []))
    config = store.reset_local_only(port=args.port or (previous.port if previous else 8765))
    auth = AuthService(root / "data" / "auth.json")
    if auth.configured:
        auth.revoke_all_for_reason("network-reset-local-only")
        auth.audit_event("network-local-fallback", port=config.port)
    print(f"Local-only access restored: {config.primary_url}")
    print("Restart the Gpt-Bridge service.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
