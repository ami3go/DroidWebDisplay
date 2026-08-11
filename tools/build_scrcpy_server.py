#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gpt_bridge.upstream_update.build import build_matching_server


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a matching scrcpy server in an isolated workspace")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "third_party/scrcpy")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--patch-dir", type=Path)
    parser.add_argument("--command", help="Override the Gradle command; parsed with shell-like quoting but executed without a shell")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = build_matching_server(
        args.source_dir.resolve(),
        revision=args.revision,
        output=args.output.resolve(),
        patch_directory=args.patch_dir.resolve() if args.patch_dir else None,
        command=shlex.split(args.command, posix=sys.platform != "win32") if args.command else None,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
