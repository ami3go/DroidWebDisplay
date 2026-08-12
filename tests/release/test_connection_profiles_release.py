from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_generated_openapi_contains_authenticated_profile_contract() -> None:
    document = json.loads((ROOT / "packages/bridge-api/openapi/openapi-v1.json").read_text(encoding="utf-8"))
    paths = document["paths"]
    required = {
        "/api/v1/profiles",
        "/api/v1/profiles/{profile_id}",
        "/api/v1/profiles/{profile_id}/default",
        "/api/v1/profiles/default",
        "/api/v1/profiles/{profile_id}/used",
    }
    assert required <= set(paths)
    for path in required:
        for operation in paths[path].values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue
            assert operation.get("security"), f"{path} must remain behind trusted-session authentication"

    profile_schema = document["components"]["schemas"]["ConnectionProfileInput"]
    serialized = json.dumps(profile_schema).lower()
    for forbidden in ("pin", "privatekey", "firewall", "allowednetworks", "trustedsession"):
        assert forbidden not in serialized


def test_committed_web_runtime_contains_complete_profile_workflow() -> None:
    runtime = ROOT / "apps/web-client/dist/assets/connection-profile-controller.js"
    assert runtime.is_file(), "connection profile TypeScript must be rebuilt into committed dist"
    source = runtime.read_text(encoding="utf-8")
    for marker in (
        "Load & Connect",
        "Waiting for exact saved device",
        "droidwebdisplay-connection-profile",
        "Auto-load this profile at startup",
        "Saved encoder",
        "Import profile",
        "Export profile",
    ):
        assert marker in source


def test_profile_runtime_keeps_display_presets_distinct_from_connection_profiles() -> None:
    source = (ROOT / "apps/web-client/src/connection-profile-controller.ts").read_text(encoding="utf-8")
    assert 'label.firstChild.textContent = "Display preset' in source
    assert 'restore.textContent = "Restore preset settings"' in source
    assert "profile.device.serial" in source
    assert "device.serial === profile.device.serial" in source
