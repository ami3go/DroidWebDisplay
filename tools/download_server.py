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
    parser = argparse.ArgumentParser(description="Verify or download the pinned compatible scrcpy server")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.repo_root.resolve()
    manifest = json.loads((root / "compatibility/scrcpy-versions.json").read_text(encoding="utf-8"))
    entry = manifest["supportedVersions"][manifest["defaultAdapter"]]
    output = (args.output or root / "server" / f"scrcpy-server-v{entry['version']}").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    expected = str(entry.get("serverSha256") or entry["officialReleaseServerSha256"]).lower()
    if output.is_file():
        actual = sha256_file(output)
        if actual == expected:
            print(f"Verified existing compatible server: {output}")
            return 0
        raise RuntimeError(f"Refusing to overwrite server with SHA-256 {actual}; expected {expected}")
    download_url = entry.get("serverUrl")
    if not download_url and expected == str(entry.get("officialReleaseServerSha256", "")).lower():
        download_url = entry.get("officialReleaseServerUrl")
    if not download_url:
        raise RuntimeError(
            "The pinned patched scrcpy server is missing. Restore it from the repository checkout "
            "or rebuild it from the recorded upstream commit and patch series."
        )
    temporary = output.with_suffix(output.suffix + ".part")
    try:
        with urllib.request.urlopen(str(download_url), timeout=120) as response, temporary.open("wb") as handle:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                handle.write(chunk)
        actual = sha256_file(temporary)
        if actual != expected:
            raise RuntimeError(f"Downloaded server SHA-256 mismatch: {actual}; expected {expected}")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Verified downloaded server: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2)
