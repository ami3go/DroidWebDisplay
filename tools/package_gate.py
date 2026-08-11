#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from droid_web_display.release_packaging import validate_release_tree


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a built DroidWebDisplay release tree")
    parser.add_argument("release_root", type=Path)
    parser.add_argument("--require-offline-ready", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_release_tree(args.release_root, require_offline_ready=args.require_offline_ready)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
