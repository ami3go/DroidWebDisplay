#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from gpt_bridge.auth import AuthService
from gpt_bridge.config import BridgeConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the PC-local Gpt-Bridge PIN and trusted sessions")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--yes", action="store_true", help="Confirm destructive reset")
    args = parser.parse_args()
    if not args.yes:
        print("Refusing to reset authentication without --yes")
        return 2
    config = BridgeConfig(repo_root=args.repo_root.resolve())
    service = AuthService(config.resolved_auth_data_file)
    service.reset()
    print(f"Reset authentication store: {config.resolved_auth_data_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
