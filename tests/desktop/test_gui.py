from __future__ import annotations

from pathlib import Path


def test_qt_desktop_host_smoke(monkeypatch) -> None:
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from droid_web_display.desktop.gui import desktop_smoke_test

    root = Path(__file__).resolve().parents[2]
    icon = root / "apps" / "web-client" / "dist" / "favicon.svg"
    assert icon.is_file()
    assert desktop_smoke_test(icon) == 0
