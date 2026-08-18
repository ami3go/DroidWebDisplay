from pathlib import Path


def test_scrcpy_control_sessions_disable_native_clipboard_autosync() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "droid_web_display/scrcpy/command.py").read_text(encoding="utf-8")

    assert 'if options.control:' in source
    assert 'args.append("clipboard_autosync=false")' in source
    assert source.index('args.append("clipboard_autosync=false")') < source.index('args.append("control=false")')
