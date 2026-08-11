import json
from pathlib import Path

from gpt_bridge.evidence import validate_runtime_browser_evidence


def test_browser_evidence_requires_video_control_and_manual_checks(tmp_path: Path) -> None:
    evidence = {
        "phase": 4,
        "status": "PASS",
        "browser": {"webCodecs": True},
        "video": {"framesDecoded": 10, "width": 864, "height": 1920},
        "session": {
            "state": "running",
            "serial": "PHONE",
            "dummyByteValidated": True,
            "channels": ["video", "control"],
            "channelDiagnostics": {
                "video": {"bytesFromDevice": 1000},
                "control": {"bytesToDevice": 64},
            },
        },
        "manualChecks": {
            "videoVisible": True,
            "clickTouch": True,
            "dragSwipe": True,
            "keyboard": True,
            "navigation": True,
            "rotation": True,
            "refreshRecovery": True,
        },
    }
    path = tmp_path / "gate4.json"
    path.write_text(json.dumps(evidence), encoding="utf-8")
    assert validate_runtime_browser_evidence(path)["status"] == "PASS"
    evidence["manualChecks"]["rotation"] = False
    path.write_text(json.dumps(evidence), encoding="utf-8")
    result = validate_runtime_browser_evidence(path)
    assert result["status"] == "FAIL"
    assert "rotation" in result["errors"][0]
