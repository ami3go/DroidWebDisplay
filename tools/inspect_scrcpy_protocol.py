#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gpt_bridge.upstream_update.inspection import inspect_protocol_changes, write_protocol_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect protocol-sensitive changes between scrcpy revisions")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "third_party/scrcpy")
    parser.add_argument("--base", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = inspect_protocol_changes(args.source_dir.resolve(), args.base, args.target)
    paths = write_protocol_report(report, args.output_dir.resolve())
    print(json.dumps({"status": "PASS", "reports": paths, "risk": report["risk"]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
