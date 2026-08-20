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
    assert 'TAB_NAMES = ("Overview", "Logs", "Diagnostics", "Settings")' in gui
    assert "QTabWidget" in gui
    assert 'setObjectName("mainTabs")' in gui
    assert 'self.resize(760, 600)' in gui
    assert 'self.setMinimumSize(640, 520)' in gui
    assert 'windowGeometryTabsV1' in gui


def test_overview_merges_summary_and_live_health_side_by_side() -> None:
    gui = (ROOT / "droid_web_display/desktop/gui.py").read_text(encoding="utf-8")
    assert 'self._tabs.addTab(self._build_health_tab(), "Health")' not in gui
    assert "def _build_health_tab" not in gui
    assert '_make_card("Summary")' in gui
    assert '"Health status",' in gui
    assert "overview_row = QHBoxLayout()" in gui
    assert "overview_row.addWidget(summary, 1)" in gui
    assert "overview_row.addWidget(health, 1)" in gui
    assert 'QPushButton("Run health check")' not in gui
    assert 'self._tabs.tabText(self._tabs.currentIndex()) == "Logs"' in gui


def test_primary_open_and_exit_actions_live_in_header_as_icons() -> None:
    gui = (ROOT / "droid_web_display/desktop/gui.py").read_text(encoding="utf-8")
    assert 'brand_icon.setObjectName("brandIcon")' in gui
    assert 'brand_title = QLabel("DroidWebDisplay")' in gui
    assert "QStyle.StandardPixmap.SP_DesktopIcon" in gui
    assert "QStyle.StandardPixmap.SP_TitleBarCloseButton" in gui
    assert "header_layout.addWidget(self._status_value" in gui
    assert "header_layout.addWidget(self._header_open_button" in gui
    assert "header_layout.addWidget(self._header_exit_button" in gui
    # Assert on the user-visible strings, not on a local variable name: the old
    # form passed if the footer button came back as `open_btn = QPushButton(...)`.
    assert gui.count('QPushButton("Open DroidWebDisplay")') == 0
    assert gui.count('QPushButton("Exit")') == 0


def test_summary_is_compact_and_local_url_is_clickable() -> None:
    gui = (ROOT / "droid_web_display/desktop/gui.py").read_text(encoding="utf-8")
    assert "summary_layout.addStretch(1)" in gui
    assert '("Local URL", self._url_value)' in gui
    assert 'self._url_value.setObjectName("summaryUrl")' in gui
    assert "Qt.TextBrowserInteraction" in gui
    assert "self._url_value.linkActivated.connect(self._open_summary_url)" in gui
    assert "QDesktopServices.openUrl(QUrl(href))" in gui
    # The link must only be offered while the server can serve it, matching the
    # gating on the header Open button.
    assert "url_is_live = snapshot.state in {ServerState.RUNNING, ServerState.EXTERNAL}" in gui
    assert 'style="color:#82a6ff' not in gui


def test_settings_include_only_minimal_update_checker() -> None:
    gui = (ROOT / "droid_web_display/desktop/gui.py").read_text(encoding="utf-8")
    assert '_make_card("Updates"' in gui or '"Updates",' in gui
    assert 'QPushButton("Check for updates")' in gui
    assert 'QPushButton("Open release page")' in gui
    assert 'self._update_channel.addItems(["Stable", "Pre-release"])' in gui
    assert 'Configuration backup' not in gui
    assert 'Tray notifications' not in gui
    assert 'Live event timeline' not in gui


def test_settings_tab_scrolls_instead_of_compressing_cards() -> None:
    gui = (ROOT / "droid_web_display/desktop/gui.py").read_text(encoding="utf-8")
    assert "QScrollArea" in gui
    assert 'scroll.setObjectName("settingsScroll")' in gui
    assert "scroll.setWidgetResizable(True)" in gui
    assert "QLayout.SizeConstraint.SetMinimumSize" in gui
    assert "Qt.ScrollBarPolicy.ScrollBarAlwaysOff" in gui
    assert "scroll.setWidget(page)" in gui
    assert "return scroll" in gui
