#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from droid_web_display.upstream_update.compatibility import promote_adapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a scrcpy adapter only when required evidence is present")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--status", choices=("experimental", "candidate", "stable"), required=True)
    parser.add_argument("--automated-evidence", action="append", default=[])
    parser.add_argument("--browser-evidence", action="append", default=[])
    parser.add_argument("--hardware-evidence", action="append", default=[])
    parser.add_argument("--make-default", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = promote_adapter(
        args.repo_root.resolve(),
        target_adapter=args.adapter,
        status=args.status,
        automated_evidence=args.automated_evidence,
        browser_evidence=args.browser_evidence,
        hardware_evidence=args.hardware_evidence,
        make_default=args.make_default,
    )
    print(json.dumps({"status": "PASS", **result}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
