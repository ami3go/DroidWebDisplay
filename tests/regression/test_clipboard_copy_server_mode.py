from droid_web_display.models import SessionOptions
from droid_web_display.scrcpy.command import build_server_arguments


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
