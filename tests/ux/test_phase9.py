from pathlib import Path

from droid_web_display.models import ChannelName, SessionOptions
from droid_web_display.scrcpy.command import build_server_arguments
from droid_web_display.transfers.paths import normalize_android_path


ROOT = Path(__file__).resolve().parents[2]


def test_requested_button_labels_and_legacy_gate_controls_are_removed() -> None:
    html = (ROOT / "apps/web-client/dist/index.html").read_text(encoding="utf-8")
    assert '>Load<' not in html
    assert '>Browse<' not in html
    assert '>Download<' in html
    assert '>Reset<' in html
    assert "Android File Explorer" in html
    assert "Custom PC folder" in html
    for old in ("Upload selected file(s)", "Browse upload folder", "Download selected", "Reset history", ">Upload<"):
        assert old not in html
    assert "data-gate4-check" not in html
    assert "data-gate5-check" not in html
    assert "data-gate6-check" not in html
    assert "data-gate7-check" not in html
    assert "verification" not in html


def test_phase9_native_layout_audio_clipboard_and_reconnect_controls_are_bundled() -> None:
    html = (ROOT / "apps/web-client/dist/index.html").read_text(encoding="utf-8")
    css = (ROOT / "apps/web-client/dist/styles.css").read_text(encoding="utf-8")
    for element_id in (
        'id="audio-enabled"', 'id="audio-mute"', 'id="audio-volume"',
        'id="auto-reconnect"', 'id="reconnect"',
        'id="clipboard-auto-sync"', 'id="clipboard-max-kib"',
        'id="clipboard-copy-android"', 'id="settings-export"', 'id="settings-import"',
        'id="gb-single-drawer-root"',
    ):
        assert element_id in html
    assert 'data-ui="droidwebdisplay-native-single-drawer-v1"' in html
    assert 'id="workspace-layout"' not in html
    assert '<aside class="sidepanel">' not in html
    assert '<aside class="transfer-panel"' not in html
    assert "#screen { cursor: default; }" in css
    assert ".uniform-buttons > button" in css
    assert "<h2>Audio</h2>" in html
    assert "Audio experimental" not in html
    assert "Experimental:" not in html
    assert "Browser audio may have interruptions or delay" in html
    assert 'id="auto-upload-enabled"' in html
    assert 'id="auto-upload-duplicate"' in html
    assert 'id="auto-upload-existing"' in html
    assert 'id="exit-focus"' not in html
    assert "<h2>Controls</h2>" not in html
    assert 'class="status-ring-progress"' in html
    assert "connection-ring-spin" in css
    assert ">Paste</button>" in html
    assert ">Type</button>" in html
    assert ">Copy</button>" in html
    for group in ("display", "clipboard", "files", "audio", "access", "diagnostics", "settings"):
        assert f'data-group="{group}"' in html

def test_audio_server_mapping_uses_opus_and_keeps_channel_order() -> None:
    options = SessionOptions(audio=True, audio_codec="opus", audio_bit_rate=128_000)
    args = build_server_arguments("4.1", 0x12345678, options)
    assert "audio=false" not in args
    assert not any(value.startswith("audio_codec=") for value in args)
    assert not any(value.startswith("audio_bit_rate=") for value in args)
    assert options.ordered_channels() == (ChannelName.VIDEO, ChannelName.AUDIO, ChannelName.CONTROL)

    aac = build_server_arguments("4.1", 0x12345678, SessionOptions(audio=True, audio_codec="aac", audio_bit_rate=96_000))
    assert "audio_codec=aac" in aac
    assert "audio_bit_rate=96000" in aac


def test_internal_documents_case_and_external_sd_paths_are_canonical() -> None:
    assert normalize_android_path("/sdcard/documents/Report.pdf") == "/sdcard/Documents/Report.pdf"
    assert normalize_android_path("/storage/ABCD-1234/Documents/report.pdf") == "/storage/ABCD-1234/Documents/report.pdf"
    assert normalize_android_path("/mnt/media_rw/ABCD-1234/DCIM/photo.jpg") == "/storage/ABCD-1234/DCIM/photo.jpg"


def test_automatic_clipboard_sync_does_not_prompt_loop_or_auto_paste() -> None:
    root = Path(__file__).resolve().parents[2]
    controller = (root / "apps/web-client/src/controller.ts").read_text(encoding="utf-8")
    html = (root / "apps/web-client/static/index.html").read_text(encoding="utf-8")
    assert "clipboardMessage(text, sequence, false)" in controller
    assert 'pasteText(text, "automatic PC clipboard")' not in controller
    assert "if (requestPermission)" in controller
    assert 'permissionState !== "granted"' in controller
    assert "#clipboardReadAllowed" in controller
    assert "Automatic sync mirrors clipboard content only" in html


def test_virtual_keyboard_suppression_and_keyboard_clipboard_shortcuts() -> None:
    html = (ROOT / "apps/web-client/static/index.html").read_text(encoding="utf-8")
    controller = (ROOT / "apps/web-client/src/controller.ts").read_text(encoding="utf-8")
    assert 'id="virtual-hide-keyboard"' in html
    assert "Virtual display only. Phone screen mode keeps the normal Android keyboard behavior." in html
    # Ctrl+V rides the native paste event from a document listener; a keydown
    # branch or a canvas-scoped listener would make it silently dead once focus
    # leaves the canvas, which the app itself causes.
    assert 'document.addEventListener("paste"' in controller
    assert 'pasteText(text, "Ctrl+V")' in controller
    assert "isEditableTarget(event.target)" in controller
    assert 'shortcut === "paste"' not in controller
    assert 'canvas.addEventListener("paste"' not in controller
    assert "androidClipboardCopyMessage()" in controller
    assert 'hideVirtualKeyboard.checked ? "hide"' in controller
