from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

PINNED_SCRCPY_COMMIT = "2926c06c5dc3064ae6d8db706f1a98a37cfcf3f0"
PINNED_SCRCPY_VERSION = "4.1"


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unable to read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def validate_protocol_sources(repo_root: Path) -> dict[str, Any]:
    package_root = repo_root / "packages" / "scrcpy-protocol"
    manifest_path = package_root / "protocol-sources.json"
    manifest = _read_json(manifest_path)
    errors: list[str] = []
    checked_sources = 0
    checked_implementations = 0

    if manifest.get("schemaVersion") != 1:
        errors.append("unsupported protocol source manifest schema")
    if manifest.get("scrcpyVersion") != PINNED_SCRCPY_VERSION:
        errors.append("protocol source manifest scrcpy version mismatch")
    if manifest.get("upstreamCommit") != PINNED_SCRCPY_COMMIT:
        errors.append("protocol source manifest commit mismatch")

    evidence = manifest.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        errors.append("protocol source manifest has no evidence entries")
        evidence = []

    for index, entry in enumerate(evidence):
        if not isinstance(entry, dict):
            errors.append(f"evidence[{index}] is not an object")
            continue
        feature = entry.get("feature")
        if not isinstance(feature, str) or not feature:
            errors.append(f"evidence[{index}] has no feature name")
            feature = f"entry-{index}"

        implementations = entry.get("implementation")
        if not isinstance(implementations, list) or not implementations:
            errors.append(f"{feature}: no implementation paths")
            implementations = []
        for relative in implementations:
            if not isinstance(relative, str):
                errors.append(f"{feature}: invalid implementation path")
                continue
            target = package_root / relative
            if not target.is_file():
                errors.append(f"{feature}: implementation file missing: {relative}")
            checked_implementations += 1

        sources = entry.get("sources")
        if not isinstance(sources, list) or not sources:
            errors.append(f"{feature}: no pinned source references")
            sources = []
        for source in sources:
            if not isinstance(source, dict):
                errors.append(f"{feature}: invalid source reference")
                continue
            url = source.get("url")
            path = source.get("path")
            lines = source.get("lines")
            if not isinstance(path, str) or not path:
                errors.append(f"{feature}: source path is missing")
            if not isinstance(url, str) or PINNED_SCRCPY_COMMIT not in url:
                errors.append(f"{feature}: source URL is not pinned to the exact commit")
            if not isinstance(lines, list) or not lines:
                errors.append(f"{feature}: source line ranges are missing")
            else:
                for line_range in lines:
                    if (
                        not isinstance(line_range, list)
                        or len(line_range) != 2
                        or not all(isinstance(value, int) for value in line_range)
                        or line_range[0] < 1
                        or line_range[1] < line_range[0]
                    ):
                        errors.append(f"{feature}: invalid source line range: {line_range!r}")
            checked_sources += 1

    return {
        "status": "PASS" if not errors else "FAIL",
        "manifest": str(manifest_path),
        "upstreamCommit": manifest.get("upstreamCommit"),
        "features": len(evidence),
        "implementationFiles": checked_implementations,
        "sourceReferences": checked_sources,
        "errors": errors,
    }


def validate_fixture_manifest(repo_root: Path) -> dict[str, Any]:
    fixture_root = repo_root / "packages" / "scrcpy-protocol" / "fixtures"
    manifest_path = fixture_root / "manifest.json"
    manifest = _read_json(manifest_path)
    errors: list[str] = []
    results: list[dict[str, Any]] = []

    if manifest.get("schemaVersion") != 1:
        errors.append("unsupported fixture manifest schema")
    if manifest.get("scrcpyVersion") != PINNED_SCRCPY_VERSION:
        errors.append("fixture scrcpy version mismatch")
    if manifest.get("upstreamCommit") != PINNED_SCRCPY_COMMIT:
        errors.append("fixture commit mismatch")

    fixtures = manifest.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        errors.append("fixture manifest has no fixtures")
        fixtures = []

    seen: set[str] = set()
    for index, entry in enumerate(fixtures):
        if not isinstance(entry, dict):
            errors.append(f"fixture[{index}] is not an object")
            continue
        name = entry.get("file")
        if not isinstance(name, str) or not name:
            errors.append(f"fixture[{index}] has no filename")
            continue
        if name in seen:
            errors.append(f"duplicate fixture: {name}")
        seen.add(name)
        path = fixture_root / name
        declared_hash = entry.get("sha256")
        declared_bytes = entry.get("bytes")
        item: dict[str, Any] = {"file": name, "path": str(path)}
        if not path.is_file():
            errors.append(f"fixture missing: {name}")
            item["status"] = "FAIL"
            results.append(item)
            continue
        actual_hash = sha256_file(path)
        actual_bytes = path.stat().st_size
        item.update({"sha256": actual_hash, "bytes": actual_bytes})
        item_errors: list[str] = []
        if declared_hash != actual_hash:
            item_errors.append("sha256 mismatch")
        if declared_bytes != actual_bytes:
            item_errors.append("size mismatch")
        if item_errors:
            errors.extend(f"{name}: {message}" for message in item_errors)
            item["status"] = "FAIL"
            item["errors"] = item_errors
        else:
            item["status"] = "PASS"
        results.append(item)

    return {
        "status": "PASS" if not errors else "FAIL",
        "manifest": str(manifest_path),
        "fixtures": results,
        "errors": errors,
    }
