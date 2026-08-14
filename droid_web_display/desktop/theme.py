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
    "warning": "#f3c969",
    "warning_surface": "#2a2412",
    "warning_border": "#7d682b",
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

QLabel[fieldLabel="true"] {{
    color: {c['text_muted']};
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

QTabWidget#mainTabs::pane {{
    border: 0;
    margin: 0;
    padding: 0;
    background-color: {c['background']};
}}

QTabBar::tab {{
    min-width: 82px;
    padding: 9px 13px;
    margin-right: 2px;
    border: 0;
    border-bottom: 2px solid transparent;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    background-color: transparent;
    color: {c['text_muted']};
    font-weight: 600;
}}

QTabBar::tab:hover {{
    color: {c['text']};
    background-color: {c['surface_alt']};
}}

QTabBar::tab:selected {{
    color: {c['text']};
    background-color: {c['surface']};
    border-bottom-color: {c['accent']};
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


QFrame#card[dashboardCard="true"] {{
    background-color: {c['surface_alt']};
}}

QLabel#dashboardValue {{
    color: {c['text']};
    font-size: 15pt;
    font-weight: 700;
}}

QLabel#dashboardDetail {{
    color: {c['text_muted']};
    font-size: 9pt;
}}

QPushButton#deviceLink {{
    min-height: 22px;
    padding: 0;
    border: 0;
    background: transparent;
    color: {c['focus']};
    font-size: 15pt;
    font-weight: 700;
    text-align: left;
}}

QPushButton#deviceLink:hover {{
    color: {c['text']};
    background: transparent;
}}

QLabel#healthStatus {{
    min-height: 18px;
    padding: 4px 10px;
    border: 1px solid #465064;
    border-radius: 11px;
    background-color: #121720;
    color: {c['text_secondary']};
    font-size: 9pt;
    font-weight: 700;
}}

QLabel#healthStatus[healthState="ok"] {{
    border-color: {c['success_border']};
    background-color: {c['success_surface']};
    color: {c['success']};
}}

QLabel#healthStatus[healthState="warn"] {{
    border-color: {c['warning_border']};
    background-color: {c['warning_surface']};
    color: {c['warning']};
}}

QLabel#healthStatus[healthState="error"] {{
    border-color: {c['danger_border']};
    background-color: {c['danger_surface']};
    color: #ffd4dc;
}}

QLabel#footerDevice {{
    color: {c['text_muted']};
    font-size: 9pt;
    font-weight: 600;
}}

QLabel#footerDevice[deviceState="ok"] {{
    color: {c['success']};
}}

QLabel#footerDevice[deviceState="error"] {{
    color: #ffd4dc;
}}

QFrame#footer {{
    border-top: 1px solid {c['border']};
    background: transparent;
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

QLineEdit, QComboBox, QPlainTextEdit#logView {{
    border: 1px solid {c['border_strong']};
    border-radius: 8px;
    background-color: {c['surface_alt']};
    color: {c['text']};
    selection-background-color: {c['accent']};
}}

QLineEdit, QComboBox {{
    min-height: 22px;
    padding: 5px 9px;
}}

QLineEdit:focus, QComboBox:focus, QPlainTextEdit#logView:focus {{
    border-color: {c['focus']};
}}

QComboBox::drop-down {{
    border: 0;
    width: 22px;
}}

QComboBox QAbstractItemView {{
    border: 1px solid {c['border']};
    background-color: {c['surface_alt']};
    color: {c['text']};
    selection-background-color: {c['surface_button']};
    outline: 0;
}}

QPlainTextEdit#logView {{
    padding: 9px;
    font-family: "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 9pt;
}}


QPlainTextEdit#timelineView {{
    min-height: 118px;
    padding: 9px;
    font-family: "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 9pt;
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
