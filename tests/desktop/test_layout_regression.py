from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_card_headers_are_inside_cards() -> None:
    gui = (ROOT / "droid_web_display/desktop/gui.py").read_text(encoding="utf-8")
    theme = (ROOT / "droid_web_display/desktop/theme.py").read_text(encoding="utf-8")
    assert "QGroupBox" not in gui
    assert "QGroupBox::title" not in theme
    assert 'setObjectName("card")' in gui
    assert 'setObjectName("cardTitle")' in gui
    assert "QFrame#card" in theme


def test_manager_uses_fixed_application_tabs_and_compact_default_size() -> None:
    gui = (ROOT / "droid_web_display/desktop/gui.py").read_text(encoding="utf-8")
    assert 'TAB_NAMES = ("Overview", "Health", "Logs", "Diagnostics", "Settings")' in gui
    assert "QTabWidget" in gui
    assert 'setObjectName("mainTabs")' in gui
    assert 'self.resize(760, 600)' in gui
    assert 'self.setMinimumSize(640, 520)' in gui
    assert 'windowGeometryTabsV1' in gui


def test_primary_open_and_exit_actions_live_outside_tabs() -> None:
    gui = (ROOT / "droid_web_display/desktop/gui.py").read_text(encoding="utf-8")
    assert 'footer.setObjectName("footer")' in gui
    assert 'footer_open = QPushButton("Open DroidWebDisplay")' in gui
    assert 'footer_exit = QPushButton("Exit")' in gui
