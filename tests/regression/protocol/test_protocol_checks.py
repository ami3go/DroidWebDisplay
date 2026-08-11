from __future__ import annotations

import json
from pathlib import Path

from gpt_bridge.scrcpy.protocol_checks import (
    PINNED_SCRCPY_COMMIT,
    validate_fixture_manifest,
    validate_protocol_sources,
)

ROOT = Path(__file__).resolve().parents[3]


def test_protocol_sources_are_exactly_pinned_and_complete() -> None:
    result = validate_protocol_sources(ROOT)
    assert result["status"] == "PASS", result
    assert result["upstreamCommit"] == PINNED_SCRCPY_COMMIT
    assert result["features"] >= 6
    assert result["sourceReferences"] >= 10


def test_fixture_hashes_and_sizes_match_manifest() -> None:
    result = validate_fixture_manifest(ROOT)
    assert result["status"] == "PASS", result
    assert len(result["fixtures"]) >= 3
    assert all(item["status"] == "PASS" for item in result["fixtures"])


def test_compatibility_manifest_points_to_v41_adapter_evidence() -> None:
    manifest = json.loads((ROOT / "compatibility" / "scrcpy-versions.json").read_text(encoding="utf-8"))
    entry = manifest["supportedVersions"]["scrcpy-4.1"]
    assert entry["upstreamCommit"] == PINNED_SCRCPY_COMMIT
    assert entry["adapterModule"] == "versions/v4_1"
    assert entry["status"] == "stable"
    assert "packages/scrcpy-protocol/protocol-sources.json" in entry["protocolEvidence"]
