from __future__ import annotations

from PySide6.QtWidgets import QApplication

# Keep the desktop server manager visually aligned with apps/web-client/static/styles.css.
# These are the primary web UI tokens rather than an independent desktop palette.
WEB_THEME = {
    "background": "#0a0d13",
    "surface": "#141923",
    "surface_alt": "#101620",
    "surface_button": "#252c39",
    "surface_button_hover": "#30394b",
    "border": "#2c3445",
    "border_strong": "#343d50",
    "text": "#f3f6fb",
    "text_secondary": "#aeb7c8",
    "text_muted": "#8f9bb0",
    "accent": "#5d7cff",
    "accent_hover": "#6d89ff",
    "focus": "#82a6ff",
    "success": "#69d9a2",
    "success_surface": "#10251d",
    "success_border": "#2f8061",
    "danger": "#a63f53",
    "danger_hover": "#b84a60",
    "danger_surface": "#4c1e28",
    "danger_border": "#8d3b4d",
}


def desktop_stylesheet() -> str:
    c = WEB_THEME
    return f"""
QWidget {{
    background-color: {c['background']};
    color: {c['text']};
    font-family: Inter, "Segoe UI", sans-serif;
    font-size: 10pt;
}}

QMainWindow, QMessageBox, QDialog {{
    background-color: {c['background']};
}}

QWidget#serverRoot {{
    background-color: {c['background']};
}}

QLabel {{
    background: transparent;
}}

QLabel#brandTitle {{
    color: {c['text']};
    font-size: 18pt;
    font-weight: 700;
}}

QLabel#brandSubtitle, QLabel#sectionHint {{
    color: {c['text_muted']};
    font-size: 9pt;
}}

QLabel[fieldValue="true"] {{
    color: {c['text']};
    font-weight: 600;
}}

QLabel[errorValue="true"] {{
    color: {c['text_secondary']};
}}

QLabel#statusPill {{
    min-height: 20px;
    padding: 5px 11px;
    border: 1px solid #4c5669;
    border-radius: 12px;
    background-color: #121720;
    color: #9ca8ba;
    font-size: 9pt;
    font-weight: 700;
}}

QLabel#statusPill[serverState="running"],
QLabel#statusPill[serverState="external"] {{
    border-color: {c['success_border']};
    background-color: {c['success_surface']};
    color: {c['success']};
}}

QLabel#statusPill[serverState="starting"],
QLabel#statusPill[serverState="stopping"] {{
    border-color: #506da8;
    background-color: #111a2a;
    color: {c['focus']};
}}

QLabel#statusPill[serverState="error"] {{
    border-color: {c['danger_border']};
    background-color: {c['danger_surface']};
    color: #ffd4dc;
}}

QFrame#card {{
    border: 1px solid {c['border']};
    border-radius: 14px;
    background-color: {c['surface']};
}}

QLabel#cardTitle {{
    color: {c['text']};
    font-size: 10pt;
    font-weight: 700;
}}

QLabel[fieldLabel="true"] {{
    color: {c['text_muted']};
}}

QFrame#card QLabel[fieldValue="true"] {{
    color: {c['text']};
}}

QFrame#card QLabel[errorValue="true"] {{
    color: {c['text_secondary']};
}}

QPushButton {{
    min-height: 20px;
    padding: 8px 13px;
    border: 1px solid {c['border_strong']};
    border-radius: 10px;
    background-color: {c['surface_button']};
    color: {c['text']};
    font-weight: 700;
}}

QPushButton:hover {{
    background-color: {c['surface_button_hover']};
    border-color: #45516a;
}}

QPushButton:pressed {{
    background-color: #1d2430;
}}

QPushButton:focus {{
    border: 1px solid {c['focus']};
}}

QPushButton:disabled {{
    color: #697487;
    background-color: #171b23;
    border-color: #242a37;
}}

QPushButton[variant="primary"] {{
    background-color: {c['accent']};
    border-color: {c['accent']};
    color: white;
}}

QPushButton[variant="primary"]:hover {{
    background-color: {c['accent_hover']};
    border-color: {c['accent_hover']};
}}

QPushButton[variant="danger"] {{
    background-color: {c['danger']};
    border-color: {c['danger']};
    color: white;
}}

QPushButton[variant="danger"]:hover {{
    background-color: {c['danger_hover']};
    border-color: {c['danger_hover']};
}}

QCheckBox {{
    spacing: 8px;
    color: {c['text_secondary']};
    background: transparent;
    padding: 3px 0;
}}

QCheckBox:disabled {{
    color: #697487;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
}}

QMenu {{
    padding: 5px;
    border: 1px solid {c['border']};
    border-radius: 9px;
    background-color: {c['surface_alt']};
    color: {c['text']};
}}

QMenu::item {{
    padding: 7px 22px 7px 10px;
    border-radius: 6px;
}}

QMenu::item:selected {{
    background-color: {c['surface_button']};
}}

QMenu::separator {{
    height: 1px;
    margin: 5px 7px;
    background-color: {c['border']};
}}

QToolTip {{
    padding: 6px 8px;
    border: 1px solid {c['border_strong']};
    border-radius: 6px;
    background-color: {c['surface_alt']};
    color: {c['text']};
}}
"""


def apply_desktop_theme(app: QApplication) -> None:
    """Apply a deterministic cross-platform theme matching the web client."""

    app.setStyle("Fusion")
    app.setStyleSheet(desktop_stylesheet())
