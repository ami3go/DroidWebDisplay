from __future__ import annotations

import json
from pathlib import Path

from gpt_bridge.evidence import validate_virtual_display_browser_evidence


def _valid_evidence() -> dict:
    checks = {
        "virtualDisplayCreated": True,
        "independentPhysicalScreen": True,
        "chatgptLaunched": True,
        "virtualInput": True,
        "virtualClipboard": True,
        "fixedDisplay": True,
        "flexDisplay": True,
        "fileTransfer": True,
        "cleanup": True,
    }
    return {
        "schemaVersion": 1,
        "phase": 6,
        "status": "PASS",
        "browser": {"webCodecs": True},
        "session": {
            "displayMode": "virtual",
            "state": "running",
            "serial": "PHONE",
            "virtualDisplay": {
                "requested": True,
                "displayId": 4,
                "requestedSize": "1600x900",
                "actualSize": "1600x900",
                "requestedDpi": 240,
                "actualDpi": 240,
                "resizeCount": 50,
            },
            "channelDiagnostics": {
                "video": {"bytesFromDevice": 1024},
                "control": {"bytesToDevice": 256},
            },
        },
        "video": {"framesDecoded": 100},
        "manualChecks": checks,
    }


def test_valid_phase6_browser_evidence(tmp_path: Path) -> None:
    path = tmp_path / "gate6-browser.json"
    path.write_text(json.dumps(_valid_evidence()), encoding="utf-8")
    result = validate_virtual_display_browser_evidence(path)
    assert result["status"] == "PASS"
    assert result["summary"]["displayId"] == 4


def test_phase6_evidence_rejects_missing_cleanup(tmp_path: Path) -> None:
    data = _valid_evidence()
    data["manualChecks"]["cleanup"] = False
    path = tmp_path / "gate6-browser.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = validate_virtual_display_browser_evidence(path)
    assert result["status"] == "FAIL"
    assert any("cleanup" in error for error in result["errors"])
