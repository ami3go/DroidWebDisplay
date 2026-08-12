from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_openapi_exposes_compatibility_not_legacy_benchmark_route() -> None:
    document = json.loads(
        (ROOT / "packages" / "bridge-api" / "openapi" / "openapi-v1.json").read_text(encoding="utf-8")
    )
    paths = document["paths"]
    assert "/api/v1/devices/{serial}/video-encoders/compatibility" in paths
    assert "/api/v1/devices/{serial}/video-encoders/benchmark" not in paths


def test_web_ui_uses_canonical_compatibility_endpoint() -> None:
    source = (ROOT / "apps" / "web-client" / "static" / "droidwebdisplay-main-drawer.js").read_text(
        encoding="utf-8"
    )
    assert "video-encoders/compatibility" in source
    assert "video-encoders/benchmark" not in source
    assert "data.compatibilityChecks || data.benchmarks || []" in source
