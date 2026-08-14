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

def test_default_window_is_tall_enough_for_manager() -> None:
    gui = (ROOT / "droid_web_display/desktop/gui.py").read_text(encoding="utf-8")
    assert "self.resize(700, 760)" in gui
    assert "self.setMinimumSize(580, 600)" in gui
