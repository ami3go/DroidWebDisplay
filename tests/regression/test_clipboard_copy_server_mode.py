import hashlib
import json
from pathlib import Path

from droid_web_display.models import SessionOptions
from droid_web_display.scrcpy.command import build_server_arguments


ROOT = Path(__file__).resolve().parents[2]


def test_scrcpy_control_sessions_keep_native_clipboard_autosync() -> None:
    args = build_server_arguments("4.1", 0x12345678, SessionOptions())

    assert "clipboard_autosync=false" not in args
    assert "control=false" not in args


def test_scrcpy_non_control_sessions_disable_only_control_channel() -> None:
    args = build_server_arguments(
        "4.1",
        0x12345678,
        SessionOptions(control=False, video=True),
    )

    assert "control=false" in args
    assert "clipboard_autosync=false" not in args


def test_pinned_server_contains_deterministic_manual_clipboard_patch() -> None:
    manifest = json.loads((ROOT / "compatibility/scrcpy-versions.json").read_text(encoding="utf-8"))
    entry = manifest["supportedVersions"][manifest["defaultAdapter"]]
    server = ROOT / entry["serverPath"]

    assert server.is_file()
    assert hashlib.sha256(server.read_bytes()).hexdigest() == entry["serverSha256"]
    assert entry["serverSha256"] != entry["officialReleaseServerSha256"]
    assert entry["serverProvenance"] == "droidwebdisplay-patched"
    assert len(entry["patchSeries"]) == 1

    patch = entry["patchSeries"][0]
    patch_path = ROOT / patch["path"]
    assert hashlib.sha256(patch_path.read_bytes()).hexdigest() == patch["sha256"]
    patch_source = patch_path.read_text(encoding="utf-8")
    assert "!clipboardAutosync || copyOrCutInjected" in patch_source
    assert "copyOrCutInjected = pressReleaseKeycode" in patch_source
