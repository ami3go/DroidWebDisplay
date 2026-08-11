from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# Evidence schema originally introduced with release gate 4.
def validate_runtime_browser_evidence(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "path": str(path), "errors": [str(exc)]}

    if data.get("phase") != 4:
        errors.append("phase must be 4")
    if data.get("status") != "PASS":
        errors.append("browser evidence status is not PASS")
    browser = data.get("browser") or {}
    if browser.get("webCodecs") is not True:
        errors.append("WebCodecs was not confirmed")
    video = data.get("video") or {}
    if int(video.get("framesDecoded") or 0) <= 0:
        errors.append("no decoded video frames were recorded")
    if int(video.get("width") or 0) <= 0 or int(video.get("height") or 0) <= 0:
        errors.append("decoded video dimensions are invalid")
    session = data.get("session") or {}
    if session.get("state") != "running":
        errors.append("session was not running when evidence was exported")
    if session.get("dummyByteValidated") is not True:
        errors.append("scrcpy dummy byte was not validated")
    channels = set(session.get("channels") or [])
    if not {"video", "control"}.issubset(channels):
        errors.append("video and control channels were not both enabled")
    diagnostics = session.get("channelDiagnostics") or {}
    if int((diagnostics.get("video") or {}).get("bytesFromDevice") or 0) <= 0:
        errors.append("video WebSocket reported no device bytes")
    if int((diagnostics.get("control") or {}).get("bytesToDevice") or 0) <= 0:
        errors.append("control WebSocket reported no browser-to-device bytes")
    manual = data.get("manualChecks") or {}
    expected = {
        "videoVisible",
        "clickTouch",
        "dragSwipe",
        "keyboard",
        "navigation",
        "rotation",
        "refreshRecovery",
    }
    missing = sorted(expected - set(manual))
    if missing:
        errors.append(f"missing manual checks: {', '.join(missing)}")
    failed = sorted(name for name in expected if manual.get(name) is not True)
    if failed:
        errors.append(f"manual checks not confirmed: {', '.join(failed)}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "path": str(path),
        "errors": errors,
        "summary": {
            "serial": session.get("serial"),
            "framesDecoded": video.get("framesDecoded"),
            "dimensions": [video.get("width"), video.get("height")],
            "videoBytes": (diagnostics.get("video") or {}).get("bytesFromDevice"),
            "controlBytes": (diagnostics.get("control") or {}).get("bytesToDevice"),
        },
    }


# Evidence schema originally introduced with release gate 5.
_REQUIRED_CHECKS_5 = {"upload", "download", "progress", "cancel", "retry", "duplicates", "videoResponsive"}


def validate_transfer_browser_evidence(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "path": str(path), "errors": [str(exc)]}
    if payload.get("schemaVersion") != 1:
        errors.append("unsupported schemaVersion")
    if payload.get("phase") != 5:
        errors.append("evidence phase must be 5")
    checks = payload.get("manualChecks")
    if not isinstance(checks, dict):
        errors.append("manualChecks is missing")
        checks = {}
    missing = sorted(_REQUIRED_CHECKS_5 - set(checks))
    if missing:
        errors.append(f"missing manual checks: {', '.join(missing)}")
    failed = sorted(name for name in _REQUIRED_CHECKS_5 if checks.get(name) is not True)
    if failed:
        errors.append(f"manual checks not passed: {', '.join(failed)}")
    transfers = payload.get("transfers")
    if not isinstance(transfers, list):
        errors.append("transfers list is missing")
        transfers = []
    completed = [item for item in transfers if isinstance(item, dict) and item.get("state") == "completed"]
    for direction in ("upload", "download"):
        if not any(item.get("direction") == direction and item.get("verification") == "size-match" for item in completed):
            errors.append(f"no completed verified {direction} transfer in evidence")
    return {
        "status": "PASS" if not errors else "FAIL",
        "path": str(path),
        "errors": errors,
        "completedTransfers": len(completed),
    }


# Evidence schema originally introduced with release gate 6.
_REQUIRED_CHECKS_6 = {
    "virtualDisplayCreated",
    "independentPhysicalScreen",
    "chatgptLaunched",
    "virtualInput",
    "virtualClipboard",
    "fixedDisplay",
    "flexDisplay",
    "fileTransfer",
    "cleanup",
}


def validate_virtual_display_browser_evidence(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "path": str(path), "errors": [str(exc)]}

    if data.get("schemaVersion") != 1:
        errors.append("unsupported schemaVersion")
    if data.get("phase") != 6:
        errors.append("evidence phase must be 6")
    if data.get("status") != "PASS":
        errors.append("browser evidence status is not PASS")
    browser = data.get("browser") or {}
    if browser.get("webCodecs") is not True:
        errors.append("WebCodecs was not confirmed")
    session = data.get("session") or {}
    if session.get("displayMode") != "virtual":
        errors.append("session was not a virtual-display session")
    if session.get("state") != "running":
        errors.append("session was not running when evidence was exported")
    virtual = session.get("virtualDisplay") or {}
    if not isinstance(virtual.get("displayId"), int):
        errors.append("virtual display ID is missing")
    if virtual.get("requested") is not True:
        errors.append("virtual display request is not recorded")
    if int(virtual.get("requestedDpi") or 0) <= 0:
        errors.append("requested virtual-display DPI is missing")
    diagnostics = session.get("channelDiagnostics") or {}
    if int((diagnostics.get("video") or {}).get("bytesFromDevice") or 0) <= 0:
        errors.append("video channel reported no device bytes")
    if int((diagnostics.get("control") or {}).get("bytesToDevice") or 0) <= 0:
        errors.append("control channel reported no browser-to-device bytes")
    video = data.get("video") or {}
    if int(video.get("framesDecoded") or 0) <= 0:
        errors.append("no decoded video frames were recorded")
    manual = data.get("manualChecks") or {}
    if not isinstance(manual, dict):
        errors.append("manualChecks is missing")
        manual = {}
    missing = sorted(_REQUIRED_CHECKS_6 - set(manual))
    if missing:
        errors.append(f"missing manual checks: {', '.join(missing)}")
    failed = sorted(name for name in _REQUIRED_CHECKS_6 if manual.get(name) is not True)
    if failed:
        errors.append(f"manual checks not confirmed: {', '.join(failed)}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "path": str(path),
        "errors": errors,
        "summary": {
            "serial": session.get("serial"),
            "displayId": virtual.get("displayId"),
            "requestedSize": virtual.get("requestedSize"),
            "actualSize": virtual.get("actualSize"),
            "dpi": virtual.get("actualDpi") or virtual.get("requestedDpi"),
            "resizeCount": virtual.get("resizeCount"),
            "framesDecoded": video.get("framesDecoded"),
        },
    }


# Evidence schema originally introduced with release gate 7.
_REQUIRED_CHECKS_7 = {
    "internalDownloads",
    "stableDetection",
    "automaticPull",
    "deduplication",
    "restartPersistence",
    "optionalDeletion",
    "sessionIsolation",
    "topAlignment",
}


def validate_auto_download_browser_evidence(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "path": str(path), "errors": [str(exc)]}
    if payload.get("schemaVersion") != 1:
        errors.append("unsupported schemaVersion")
    if payload.get("phase") != 7:
        errors.append("evidence phase must be 7")
    if payload.get("status") != "PASS":
        errors.append("browser evidence status is not PASS")
    if payload.get("displayAlignment") != "top":
        errors.append("Android display top alignment was not recorded")
    if payload.get("internalDownloadPath") != "/sdcard/Download":
        errors.append("internal storage Download path was not recorded")
    checks = payload.get("manualChecks")
    if not isinstance(checks, dict):
        errors.append("manualChecks is missing")
        checks = {}
    missing = sorted(_REQUIRED_CHECKS_7 - set(checks))
    if missing:
        errors.append(f"missing manual checks: {', '.join(missing)}")
    failed = sorted(name for name in _REQUIRED_CHECKS_7 if checks.get(name) is not True)
    if failed:
        errors.append(f"manual checks not confirmed: {', '.join(failed)}")
    snapshot = payload.get("autoDownload") or {}
    config = snapshot.get("config") or {}
    runtime = snapshot.get("runtime") or {}
    if config.get("sourcePath") != "/sdcard/Download":
        errors.append("monitor source was not internal storage Download")
    if int(runtime.get("downloadsCompleted") or 0) < 1:
        errors.append("no completed automatic download was recorded")
    return {
        "status": "PASS" if not errors else "FAIL",
        "path": str(path),
        "errors": errors,
        "summary": {
            "serial": payload.get("deviceSerial"),
            "downloadsCompleted": runtime.get("downloadsCompleted"),
            "deletionsCompleted": runtime.get("deletionsCompleted"),
            "processedFingerprints": snapshot.get("processedFingerprints"),
        },
    }


# Evidence schema originally introduced with release gate 8.
_REQUIRED_CHECKS_8 = {
    "pinSetupAndLogin",
    "trustDurationSelection",
    "individualRevocation",
    "globalRevocation",
    "expiredSessionRejected",
    "protectedApiRejected",
    "protectedWebSocketRejected",
    "pcLocalTrustWording",
}


def validate_auth_browser_evidence(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "path": str(path), "errors": [str(exc)]}
    if payload.get("schemaVersion") != 1:
        errors.append("unsupported schemaVersion")
    if payload.get("phase") != 8:
        errors.append("evidence phase must be 8")
    if payload.get("status") != "PASS":
        errors.append("browser evidence status is not PASS")
    if payload.get("trustModel") != "pc-local":
        errors.append("PC-local trust model was not recorded")
    if payload.get("phoneAuthoritative") is not False:
        errors.append("evidence must state that Android is not the trust authority")
    checks = payload.get("manualChecks")
    if not isinstance(checks, dict):
        errors.append("manualChecks is missing")
        checks = {}
    missing = sorted(_REQUIRED_CHECKS_8 - set(checks))
    if missing:
        errors.append(f"missing manual checks: {', '.join(missing)}")
    failed = sorted(name for name in _REQUIRED_CHECKS_8 if checks.get(name) is not True)
    if failed:
        errors.append(f"manual checks not confirmed: {', '.join(failed)}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "path": str(path),
        "errors": errors,
        "summary": {
            "trustModel": payload.get("trustModel"),
            "sessionCount": payload.get("trustedSessionCount"),
        },
    }

# Current UX-completion evidence schema.
_REQUIRED_CHECKS_9 = {
    "clipboardPcToAndroid",
    "clipboardAndroidToPc",
    "audioOrUnsupportedReported",
    "audioFailureIsolation",
    "fullscreenAndRotation",
    "temporaryDisconnectRecovery",
    "keyboardNavigation",
    "actionableErrors",
    "settingsRoundTrip",
    "storageRoots",
}


def validate_ux_browser_evidence(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "FAIL", "path": str(path), "errors": [str(exc)]}
    if payload.get("schemaVersion") != 1:
        errors.append("unsupported schemaVersion")
    if payload.get("phase") != 9:
        errors.append("evidence phase must be 9")
    if payload.get("status") != "PASS":
        errors.append("browser evidence status is not PASS")
    checks = payload.get("manualChecks")
    if not isinstance(checks, dict):
        errors.append("manualChecks is missing")
        checks = {}
    missing = sorted(_REQUIRED_CHECKS_9 - set(checks))
    if missing:
        errors.append(f"missing manual checks: {', '.join(missing)}")
    failed = sorted(name for name in _REQUIRED_CHECKS_9 if checks.get(name) is not True)
    if failed:
        errors.append(f"manual checks not confirmed: {', '.join(failed)}")
    browser = payload.get("browser") or {}
    if browser.get("webCodecs") is not True:
        errors.append("WebCodecs video support was not confirmed")
    if payload.get("oldGateCheckboxesPresent") is not False:
        errors.append("old gate verification checkboxes must be absent")
    return {
        "status": "PASS" if not errors else "FAIL",
        "path": str(path),
        "errors": errors,
        "summary": {
            "browser": browser.get("userAgent"),
            "audio": payload.get("audio"),
            "storageRoots": payload.get("storageRoots"),
        },
    }
