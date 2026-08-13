#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sys


def _resource_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root).resolve()
    return Path(__file__).resolve().parents[1]


def _state_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "DroidWebDisplay"
    base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    return base / "droidwebdisplay"


def _downloads_root() -> Path:
    downloads = Path.home() / "Downloads"
    if not downloads.exists():
        downloads = _state_root() / "downloads"
    return downloads / "DroidWebDisplay"


def main() -> int:
    resource_root = _resource_root()
    state_root = _state_root()
    data_root = state_root / "data"
    downloads_root = _downloads_root()
    data_root.mkdir(parents=True, exist_ok=True)
    downloads_root.mkdir(parents=True, exist_ok=True)

    adb_name = "adb.exe" if os.name == "nt" else "adb"
    adb = resource_root / "adb" / adb_name
    if not adb.is_file():
        adb = Path(adb_name)

    user_args = sys.argv[1:]
    sys.argv = [
        "DroidWebDisplay",
        "--repo-root",
        str(resource_root),
        "--data-directory",
        str(data_root),
        "--download-directory",
        str(downloads_root),
        "--network-config",
        str(data_root / "network-access.json"),
        "--adb",
        str(adb),
        "--open-browser",
        *user_args,
    ]

    from run_bridge_service import main as bridge_main

    return bridge_main()


if __name__ == "__main__":
    raise SystemExit(main())
