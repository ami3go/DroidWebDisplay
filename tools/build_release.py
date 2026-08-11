#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from droid_web_display.release_packaging import ReleaseInputs, build_release_tree, validate_release_tree


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a DroidWebDisplay platform release tree")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--target", choices=("windows", "linux", "source"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scrcpy-server", type=Path)
    parser.add_argument("--adb-directory", type=Path)
    parser.add_argument("--python-runtime", type=Path)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--allow-missing-server", action="store_true")
    parser.add_argument("--require-offline-ready", action="store_true")
    args = parser.parse_args()

    result = build_release_tree(
        args.repo_root,
        args.output,
        ReleaseInputs(
            target=args.target,
            scrcpy_server=args.scrcpy_server,
            adb_directory=args.adb_directory,
            python_runtime=args.python_runtime,
            wheelhouse=args.wheelhouse,
            allow_missing_server=args.allow_missing_server,
        ),
    )
    validation = validate_release_tree(args.output, require_offline_ready=args.require_offline_ready)
    payload = {"build": result, "validation": validation}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if validation["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
