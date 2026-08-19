from pathlib import Path


def test_scrcpy_control_sessions_keep_native_clipboard_autosync() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "droid_web_display/scrcpy/command.py").read_text(encoding="utf-8")

    assert 'args.append("clipboard_autosync=false")' not in source
    assert 'if not options.control:' in source
    assert 'args.append("control=false")' in source
