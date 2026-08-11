#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from droid_web_display.upstream_update.scaffold import scaffold_adapter


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a separate experimental scrcpy protocol adapter scaffold")
    parser.add_argument("--version", required=True)
    parser.add_argument("--base-version", required=True)
    parser.add_argument("--upstream-commit", required=True)
    parser.add_argument("--protocol-report")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    result = scaffold_adapter(
        args.repo_root.resolve(),
        version=args.version,
        base_version=args.base_version,
        upstream_commit=args.upstream_commit,
        protocol_report=args.protocol_report,
    )
    print(json.dumps({"status": "PASS", **result}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
