#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "packaging" / "supply-chain-lock.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_entry(lock_path: Path, key: str) -> dict[str, object]:
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    if data.get("schemaVersion") != 1:
        raise RuntimeError(f"Unsupported supply-chain lock schema in {lock_path}")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict) or key not in artifacts:
        raise RuntimeError(f"Unknown supply-chain artifact key: {key}")
    entry = artifacts[key]
    if not isinstance(entry, dict):
        raise RuntimeError(f"Invalid supply-chain artifact entry: {key}")
    url = entry.get("url")
    expected = entry.get("sha256")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise RuntimeError(f"{key}: artifact URL must use HTTPS")
    if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
        raise RuntimeError(f"{key}: invalid SHA-256 lock value")
    return entry


def _verify_zip_revision(path: Path, entry: dict[str, object], key: str) -> None:
    revision_path = entry.get("zipRevisionPath")
    expected_revision = entry.get("zipRevision")
    if revision_path is None and expected_revision is None:
        return
    if not isinstance(revision_path, str) or not isinstance(expected_revision, str):
        raise RuntimeError(f"{key}: zipRevisionPath and zipRevision must be specified together")
    try:
        with zipfile.ZipFile(path) as archive:
            text = archive.read(revision_path).decode("utf-8", errors="strict")
    except (KeyError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise RuntimeError(f"{key}: cannot read locked ZIP revision metadata: {exc}") from exc
    revision = None
    for line in text.splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "Pkg.Revision":
            revision = value.strip()
            break
    if revision != expected_revision:
        raise RuntimeError(
            f"{key}: ZIP revision mismatch: found {revision!r}, expected {expected_revision!r}"
        )


def _verify(path: Path, entry: dict[str, object], key: str) -> str:
    expected = str(entry["sha256"])
    actual = sha256_file(path)
    if actual != expected:
        raise RuntimeError(f"{key}: SHA-256 mismatch: found {actual}, expected {expected}")
    _verify_zip_revision(path, entry, key)
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description="Download one supply-chain artifact and verify its lock entry")
    parser.add_argument("artifact_key")
    parser.add_argument("output", type=Path)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    args = parser.parse_args()

    lock_path = args.lock.resolve()
    output = args.output.resolve()
    entry = _load_entry(lock_path, args.artifact_key)
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.is_file():
        try:
            actual = _verify(output, entry, args.artifact_key)
        except RuntimeError:
            output.unlink()
        else:
            print(
                f"Verified existing {args.artifact_key} "
                f"{entry.get('version', 'unversioned')}: sha256:{actual}"
            )
            return 0

    temporary = output.with_name(output.name + ".part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(
        str(entry["url"]),
        headers={"User-Agent": "DroidWebDisplay-supply-chain-fetch/1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as handle:
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                handle.write(chunk)
        actual = _verify(temporary, entry, args.artifact_key)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)

    print(
        f"Verified {args.artifact_key} {entry.get('version', 'unversioned')}: sha256:{actual}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
