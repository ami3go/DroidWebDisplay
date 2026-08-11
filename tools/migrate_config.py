#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from droid_web_display.release_packaging import migrate_runtime_state


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate supported DroidWebDisplay runtime configuration")
    parser.add_argument("--from", dest="previous", type=Path, required=True)
    parser.add_argument("--to", dest="new", type=Path, required=True)
    args = parser.parse_args()
    result = migrate_runtime_state(args.previous, args.new)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
