from __future__ import annotations

from pathlib import Path

from droid_web_display.desktop.theme import WEB_THEME, desktop_stylesheet


REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_STYLES = REPO_ROOT / "apps" / "web-client" / "static" / "styles.css"


def test_desktop_theme_reuses_primary_web_palette() -> None:
    web_css = WEB_STYLES.read_text(encoding="utf-8")
    shared_tokens = (
        "#0a0d13",
        "#f3f6fb",
        "#aeb7c8",
        "#8f9bb0",
        "#2c3445",
        "#343d50",
        "#5d7cff",
        "#82a6ff",
        "#69d9a2",
        "#2f8061",
        "#a63f53",
        "#8d3b4d",
    )

    theme_values = set(WEB_THEME.values())
    for token in shared_tokens:
        assert token in web_css
        assert token in theme_values


def test_desktop_stylesheet_has_modern_cards_buttons_and_state_pill() -> None:
    stylesheet = desktop_stylesheet()

    assert "border-radius: 14px" in stylesheet
    assert 'QPushButton[variant="primary"]' in stylesheet
    assert 'QPushButton[variant="danger"]' in stylesheet
    for state in ("running", "external", "starting", "stopping", "error"):
        assert f'serverState="{state}"' in stylesheet


def test_desktop_theme_remains_dark_and_bounded_to_web_tokens() -> None:
    assert WEB_THEME["background"] == "#0a0d13"
    assert WEB_THEME["surface"] == "#141923"
    assert WEB_THEME["accent"] == "#5d7cff"
    assert WEB_THEME["danger"] == "#a63f53"
    assert WEB_THEME["success"] == "#69d9a2"
