#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and verify the pinned official scrcpy server")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    manifest = json.loads((root / "compatibility/scrcpy-versions.json").read_text(encoding="utf-8"))
    entry = manifest["supportedVersions"][manifest["defaultAdapter"]]
    output = (args.output or root / "server" / f"scrcpy-server-v{entry['version']}").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    expected = entry["officialReleaseServerSha256"]
    if output.is_file():
        actual = sha256_file(output)
        if actual == expected:
            print(f"Verified existing official server: {output}")
            return 0
        raise RuntimeError(f"Refusing to overwrite server with SHA-256 {actual}; expected {expected}")
    temporary = output.with_suffix(output.suffix + ".part")
    try:
        with urllib.request.urlopen(entry["officialReleaseServerUrl"], timeout=120) as response, temporary.open("wb") as handle:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                handle.write(chunk)
        actual = sha256_file(temporary)
        if actual != expected:
            raise RuntimeError(f"Official server SHA-256 mismatch: {actual}; expected {expected}")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Verified official server: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2)
