from __future__ import annotations

import json
from pathlib import Path

from droid_web_display.evidence import validate_ux_browser_evidence


def test_phase9_browser_evidence_validation(tmp_path: Path) -> None:
    path = tmp_path / "phase9-browser.json"
    path.write_text(json.dumps({
        "schemaVersion": 1,
        "phase": 9,
        "status": "PASS",
        "browser": {"webCodecs": True, "userAgent": "test"},
        "oldGateCheckboxesPresent": False,
        "audio": {"status": "supported"},
        "storageRoots": ["/sdcard/Download", "/storage/ABCD-1234"],
        "manualChecks": {
            "clipboardPcToAndroid": True,
            "clipboardAndroidToPc": True,
            "audioOrUnsupportedReported": True,
            "audioFailureIsolation": True,
            "fullscreenAndRotation": True,
            "temporaryDisconnectRecovery": True,
            "keyboardNavigation": True,
            "actionableErrors": True,
            "settingsRoundTrip": True,
            "storageRoots": True,
        },
    }), encoding="utf-8")
    assert validate_ux_browser_evidence(path)["status"] == "PASS"
