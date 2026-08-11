#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gpt_bridge.upstream_update.patches import apply_patch_series


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a scrcpy patch series to a temporary clean workspace")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--patch-dir", type=Path, required=True)
    args = parser.parse_args()
    records = apply_patch_series(args.workspace.resolve(), args.patch_dir.resolve())
    print(json.dumps({"status": "PASS", "patches": records}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
