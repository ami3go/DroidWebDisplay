from pathlib import Path


def test_display_mode_form_is_contained_and_responsive() -> None:
    root = Path(__file__).resolve().parents[3]
    css = (root / "apps/web-client/static/styles.css").read_text(encoding="utf-8")
    assert "select { min-width: 0; max-width: 100%;" in css
    assert ".display-mode-card > label," in css
    assert ".virtual-display-settings > label," in css
    assert "display: grid;" in css
    assert ".display-mode-card select," in css
    assert "max-width: 100%;" in css
    assert ".three-field-row > label:last-child { grid-column: 1 / -1; }" in css
    assert "@media (max-width: 520px)" in css


def test_connection_device_select_keeps_desktop_minimum() -> None:
    root = Path(__file__).resolve().parents[3]
    css = (root / "apps/web-client/static/styles.css").read_text(encoding="utf-8")
    assert ".connection-row select { min-width: min(250px, 100%); }" in css
