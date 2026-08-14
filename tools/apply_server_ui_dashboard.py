from __future__ import annotations

from pathlib import Path
import re
from textwrap import dedent, indent


ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "droid_web_display/desktop/gui.py"
MONITORING = ROOT / "droid_web_display/desktop/monitoring.py"
THEME = ROOT / "droid_web_display/desktop/theme.py"
LAYOUT_TEST = ROOT / "tests/desktop/test_layout_regression.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def class_block(source: str) -> str:
    return indent(dedent(source).lstrip("\n"), "    ")


def replace_method(text: str, name: str, next_name: str, replacement: str) -> str:
    pattern = rf"    def {re.escape(name)}\(.*?(?=    def {re.escape(next_name)}\()"
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{name}: method replacement count={count}")
    return updated


def patch_gui() -> None:
    gui = GUI.read_text(encoding="utf-8")

    gui = replace_once(
        gui,
        "from __future__ import annotations\n\nimport os\n",
        "from __future__ import annotations\n\nfrom datetime import datetime, timezone\nimport os\n",
        "datetime import",
    )
    gui = replace_once(
        gui,
        "from PySide6.QtCore import QObject, QRunnable, QSettings, QThreadPool, QTimer, Qt, Signal\n"
        "from PySide6.QtGui import QAction, QCloseEvent, QIcon\n",
        "from PySide6.QtCore import QObject, QRunnable, QSettings, QThreadPool, QTimer, Qt, QUrl, Signal\n"
        "from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon\n",
        "Qt imports",
    )
    gui = replace_once(
        gui,
        "    QComboBox,\n    QFormLayout,\n    QFrame,\n    QHBoxLayout,\n",
        "    QComboBox,\n    QFileDialog,\n    QFormLayout,\n    QFrame,\n    QGridLayout,\n    QHBoxLayout,\n",
        "widget imports",
    )
    gui = replace_once(
        gui,
        "from droid_web_display.desktop.platform import StartupManager, open_directory\n"
        "from droid_web_display.desktop.support import (\n",
        "from droid_web_display.desktop.monitoring import (\n"
        "    AndroidDeviceDetails,\n"
        "    ReleaseInfo,\n"
        "    ResourceMonitor,\n"
        "    ResourceSnapshot,\n"
        "    TimelineEvent,\n"
        "    check_latest_release,\n"
        "    collect_android_device_details,\n"
        "    format_bytes,\n"
        "    read_timeline_events,\n"
        ")\n"
        "from droid_web_display.desktop.platform import StartupManager, open_directory\n"
        "from droid_web_display.desktop.settings_backup import (\n"
        "    SETTING_DEFAULTS,\n"
        "    export_desktop_settings,\n"
        "    import_desktop_settings,\n"
        "    reset_desktop_settings,\n"
        ")\n"
        "from droid_web_display.desktop.support import (\n",
        "desktop helper imports",
    )
    gui = replace_once(
        gui,
        "        self._settings = QSettings(\"DroidWebDisplay\", \"DesktopHost\")\n"
        "        self._last_log_signature: tuple[object, ...] | None = None\n",
        "        self._settings = QSettings(\"DroidWebDisplay\", \"DesktopHost\")\n"
        "        self._last_log_signature: tuple[object, ...] | None = None\n"
        "        self._resource_monitor = ResourceMonitor()\n"
        "        self._monitor_running = False\n"
        "        self._last_resource: ResourceSnapshot | None = None\n"
        "        self._last_client_hosts: set[str] | None = None\n"
        "        self._last_unauthorized_devices: set[str] | None = None\n"
        "        self._runtime_timeline: list[TimelineEvent] = []\n"
        "        self._last_log_events: list[TimelineEvent] = []\n"
        "        self._seen_timeline_keys: set[str] = set()\n"
        "        self._timeline_seeded = False\n"
        "        self._notifications_initialized = False\n"
        "        self._latest_release_url = \"\"\n",
        "monitor state",
    )

    overview = class_block(
        r'''
        def _build_overview_tab(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(2, 10, 2, 2)
            layout.setSpacing(10)

            dashboard = QGridLayout()
            dashboard.setContentsMargins(0, 0, 0, 0)
            dashboard.setHorizontalSpacing(10)
            dashboard.setVerticalSpacing(10)
            dashboard.setColumnStretch(0, 1)
            dashboard.setColumnStretch(1, 1)

            def dashboard_card(title: str, value: QWidget, detail: QLabel) -> QFrame:
                card, card_layout = _make_card(title)
                card.setProperty("dashboardCard", True)
                card_layout.setSpacing(5)
                if isinstance(value, QLabel):
                    value.setObjectName("dashboardValue")
                detail.setObjectName("dashboardDetail")
                detail.setWordWrap(True)
                card_layout.addWidget(value)
                card_layout.addWidget(detail)
                return card

            self._dashboard_server = QLabel("Starting…")
            self._dashboard_server_detail = QLabel("Waiting for server status")
            server_card = dashboard_card(
                "Server", self._dashboard_server, self._dashboard_server_detail
            )

            self._device_button = QPushButton("Checking…")
            self._device_button.setObjectName("deviceLink")
            self._device_button.setToolTip("Show Android device details")
            self._device_button.clicked.connect(self._show_android_details)
            self._dashboard_android_detail = QLabel("Checking ADB connection")
            android_card = dashboard_card(
                "Android", self._device_button, self._dashboard_android_detail
            )

            self._dashboard_clients = QLabel("0 connected")
            self._dashboard_clients_detail = QLabel("No active browser clients")
            clients_card = dashboard_card(
                "Clients", self._dashboard_clients, self._dashboard_clients_detail
            )

            self._dashboard_network = QLabel("Local only")
            self._dashboard_network_detail = QLabel("127.0.0.1")
            network_card = dashboard_card(
                "Network", self._dashboard_network, self._dashboard_network_detail
            )

            dashboard.addWidget(server_card, 0, 0)
            dashboard.addWidget(android_card, 0, 1)
            dashboard.addWidget(clients_card, 1, 0)
            dashboard.addWidget(network_card, 1, 1)

            resources, resource_layout = _make_card(
                "Resources",
                "Desktop host usage and live server connectivity.",
            )
            resource_form = QFormLayout()
            resource_form.setContentsMargins(0, 0, 0, 0)
            resource_form.setHorizontalSpacing(18)
            resource_form.setVerticalSpacing(5)
            self._metric_cpu = _field_value("—")
            self._metric_ram = _field_value("—")
            self._metric_uptime = _field_value("—")
            self._metric_network = _field_value("—")
            self._metric_clients = _field_value("0")
            self._metric_adb = _field_value("Checking…")
            for name, value in (
                ("CPU", self._metric_cpu),
                ("RAM", self._metric_ram),
                ("Process uptime", self._metric_uptime),
                ("Network RX/TX", self._metric_network),
                ("Browser clients", self._metric_clients),
                ("ADB process", self._metric_adb),
            ):
                resource_form.addRow(_field_label(name), value)
            resource_layout.addLayout(resource_form)

            timeline, timeline_layout = _make_card(
                "Live event timeline",
                "Recent server, Android, browser, display and transfer events.",
            )
            self._timeline_view = QPlainTextEdit()
            self._timeline_view.setObjectName("timelineView")
            self._timeline_view.setReadOnly(True)
            self._timeline_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
            self._timeline_view.setPlaceholderText("Live events will appear here.")
            self._timeline_view.document().setMaximumBlockCount(100)
            timeline_layout.addWidget(self._timeline_view, 1)

            live_row = QHBoxLayout()
            live_row.setContentsMargins(0, 0, 0, 0)
            live_row.setSpacing(10)
            live_row.addWidget(resources, 1)
            live_row.addWidget(timeline, 1)

            controls, controls_layout = _make_card("Server controls")
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            self._start_stop_button = QPushButton("Stop Server")
            self._start_stop_button.clicked.connect(self._toggle_server)
            _set_button_variant(self._start_stop_button, "danger")
            restart_button = QPushButton("Restart Server")
            restart_button.clicked.connect(self._restart_server)
            logs_button = QPushButton("Open Logs Folder")
            logs_button.clicked.connect(lambda: open_directory(self.controller.paths.logs_root))
            row.addWidget(self._start_stop_button)
            row.addWidget(restart_button)
            row.addWidget(logs_button)
            row.addStretch(1)
            controls_layout.addLayout(row)
            self._error_value = QLabel("Last error: None")
            self._error_value.setObjectName("sectionHint")
            self._error_value.setWordWrap(True)
            controls_layout.addWidget(self._error_value)

            layout.addLayout(dashboard)
            layout.addLayout(live_row, 1)
            layout.addWidget(controls)
            return page

        '''
    )
    gui = replace_method(gui, "_build_overview_tab", "_build_health_tab", overview)

    settings = class_block(
        r'''
        def _build_settings_tab(self) -> QWidget:
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(2, 10, 2, 2)
            layout.setSpacing(10)

            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)

            startup_card, startup_layout = _make_card("Desktop host")
            self._open_browser_checkbox = QCheckBox("Open browser when DroidWebDisplay starts")
            self._open_browser_checkbox.setChecked(
                self._settings.value("openBrowserOnStart", True, type=bool)
            )
            self._open_browser_checkbox.toggled.connect(
                lambda checked: self._settings.setValue("openBrowserOnStart", checked)
            )

            self._startup_checkbox = QCheckBox("Start DroidWebDisplay when I sign in")
            self._startup_checkbox.setEnabled(self.startup.supported)
            if self.startup.supported:
                self._startup_checkbox.setChecked(self.startup.enabled())
            self._startup_checkbox.toggled.connect(self._set_autostart)

            self._start_minimized_checkbox = QCheckBox("Start desktop host minimized")
            self._start_minimized_checkbox.setChecked(
                self._settings.value("startMinimized", False, type=bool)
            )
            self._start_minimized_checkbox.toggled.connect(
                lambda checked: self._settings.setValue("startMinimized", checked)
            )
            startup_layout.addWidget(self._open_browser_checkbox)
            startup_layout.addWidget(self._startup_checkbox)
            startup_layout.addWidget(self._start_minimized_checkbox)

            notifications, notification_layout = _make_card(
                "Tray notifications", "Only important state changes generate notifications."
            )
            self._notification_checkboxes: dict[str, QCheckBox] = {}
            notification_items = (
                ("notifyAndroid", "Android connected / disconnected"),
                ("notifyServerFailure", "Server failure"),
                ("notifyUnauthorized", "Unauthorized Android device"),
                ("notifyNewClient", "New browser client"),
                ("notifyTransferFailure", "Transfer failure"),
            )
            for key, text in notification_items:
                box = QCheckBox(text)
                box.setChecked(
                    self._settings.value(key, bool(SETTING_DEFAULTS[key]), type=bool)
                )
                box.toggled.connect(
                    lambda checked, setting_key=key: self._settings.setValue(setting_key, checked)
                )
                self._notification_checkboxes[key] = box
                notification_layout.addWidget(box)

            logging_card, logging_layout = _make_card("Logging")
            log_form = QFormLayout()
            log_form.setContentsMargins(0, 0, 0, 0)
            log_form.setHorizontalSpacing(18)
            log_form.setVerticalSpacing(6)
            log_form.addRow(
                _field_label("Level"),
                _field_value(os.environ.get("DWD_LOG_LEVEL", "INFO").upper()),
            )
            log_form.addRow(_field_label("Server rotation"), _field_value("5 MiB · 5 backups"))
            log_form.addRow(_field_label("Host rotation"), _field_value("2 MiB · 3 backups"))
            logging_layout.addLayout(log_form)
            open_logs = QPushButton("Open Log Folder")
            open_logs.clicked.connect(lambda: open_directory(self.controller.paths.logs_root))
            logging_layout.addWidget(open_logs, alignment=Qt.AlignLeft)

            config_card, config_layout = _make_card(
                "Configuration backup",
                "Exports desktop-host preferences only; trusted sessions and authentication secrets are excluded.",
            )
            config_actions = QHBoxLayout()
            config_actions.setContentsMargins(0, 0, 0, 0)
            config_actions.setSpacing(7)
            export_button = QPushButton("Export settings")
            export_button.clicked.connect(self._export_settings)
            import_button = QPushButton("Import settings")
            import_button.clicked.connect(self._import_settings)
            reset_button = QPushButton("Reset defaults")
            reset_button.clicked.connect(self._reset_settings)
            config_actions.addWidget(export_button)
            config_actions.addWidget(import_button)
            config_actions.addWidget(reset_button)
            config_layout.addLayout(config_actions)

            update_card, update_layout = _make_card("Updates")
            update_form = QFormLayout()
            update_form.setContentsMargins(0, 0, 0, 0)
            update_form.setHorizontalSpacing(18)
            update_form.setVerticalSpacing(6)
            self._update_channel = QComboBox()
            self._update_channel.addItems(["Stable", "Pre-release"])
            channel = str(self._settings.value("updateChannel", "Stable"))
            self._update_channel.setCurrentText(
                channel if channel in {"Stable", "Pre-release"} else "Stable"
            )
            self._update_channel.currentTextChanged.connect(
                lambda value: self._settings.setValue("updateChannel", value)
            )
            update_form.addRow(_field_label("DroidWebDisplay"), _field_value(__version__))
            update_form.addRow(_field_label("Release channel"), self._update_channel)
            update_layout.addLayout(update_form)
            update_actions = QHBoxLayout()
            update_actions.setContentsMargins(0, 0, 0, 0)
            update_actions.setSpacing(7)
            self._check_updates_button = QPushButton("Check for updates")
            self._check_updates_button.clicked.connect(self._check_for_updates)
            self._open_release_button = QPushButton("Open release page")
            self._open_release_button.setEnabled(False)
            self._open_release_button.clicked.connect(self._open_latest_release)
            update_actions.addWidget(self._check_updates_button)
            update_actions.addWidget(self._open_release_button)
            update_actions.addStretch(1)
            update_layout.addLayout(update_actions)
            self._update_status = QLabel("")
            self._update_status.setObjectName("sectionHint")
            self._update_status.setWordWrap(True)
            update_layout.addWidget(self._update_status)

            grid.addWidget(startup_card, 0, 0)
            grid.addWidget(notifications, 0, 1)
            grid.addWidget(logging_card, 1, 0)
            grid.addWidget(config_card, 1, 1)
            grid.addWidget(update_card, 2, 0, 1, 2)
            layout.addLayout(grid)
            layout.addStretch(1)
            return page

        '''
    )
    pattern = r"    def _build_settings_tab\(self\) -> QWidget:\n.*?(?=    @property\n    def open_browser_on_start)"
    gui, count = re.subn(pattern, settings, gui, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"settings replacement count={count}")

    support_methods = class_block(
        r'''
        def _preference_enabled(self, key: str) -> bool:
            default = bool(SETTING_DEFAULTS.get(key, True))
            return self._settings.value(key, default, type=bool)

        @staticmethod
        def _device_is_connected(value: str) -> bool:
            return bool(value) and value not in {
                "No device",
                "Checking…",
                "—",
                "ADB unavailable",
            }

        def _notify(self, preference: str, message: str, *, warning: bool = False) -> None:
            if self.tray is None or not self._preference_enabled(preference):
                return
            icon = (
                QSystemTrayIcon.MessageIcon.Warning
                if warning
                else QSystemTrayIcon.MessageIcon.Information
            )
            self.tray.showMessage("DroidWebDisplay", message, icon, 5000)

        def _record_runtime_event(self, message: str, *, kind: str = "info") -> None:
            timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            )
            self._runtime_timeline.append(
                TimelineEvent(
                    key=f"runtime-{uuid.uuid4().hex}",
                    timestamp=timestamp,
                    message=message,
                    kind=kind,
                )
            )
            self._runtime_timeline = self._runtime_timeline[-30:]
            self._refresh_timeline_display(self._last_log_events)

        def _refresh_timeline_display(self, log_events: list[TimelineEvent]) -> None:
            self._last_log_events = list(log_events)
            merged = {event.key: event for event in (*log_events, *self._runtime_timeline)}
            events = sorted(merged.values(), key=lambda event: event.timestamp)[-40:]
            self._timeline_view.setPlainText("\n".join(event.display_line() for event in events))
            scrollbar = self._timeline_view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        def _show_android_details(self) -> None:
            self._device_button.setEnabled(False)

            def completed(result: object) -> None:
                self._device_button.setEnabled(True)
                if not isinstance(result, AndroidDeviceDetails):
                    QMessageBox.information(
                        self,
                        "Android device details",
                        "No Android device is currently visible to ADB.",
                    )
                    return
                QMessageBox.information(self, "Android device details", result.summary_text())

            def failed(message: str) -> None:
                self._device_button.setEnabled(True)
                QMessageBox.warning(
                    self,
                    "Android device details",
                    f"Could not read Android device details:\n{message}",
                )

            self._start_support_task(
                lambda: collect_android_device_details(Path(self.controller.paths.adb_executable)),
                on_ready=completed,
                on_failed=failed,
            )

        def _export_settings(self) -> None:
            default_target = self.controller.paths.downloads_root / "DroidWebDisplay-settings.json"
            selected, _filter = QFileDialog.getSaveFileName(
                self,
                "Export DroidWebDisplay settings",
                str(default_target),
                "JSON files (*.json)",
            )
            if not selected:
                return
            try:
                target = export_desktop_settings(self._settings, Path(selected))
            except Exception as exc:
                QMessageBox.warning(self, "DroidWebDisplay", f"Could not export settings:\n{exc}")
                return
            QMessageBox.information(self, "DroidWebDisplay", f"Settings exported:\n{target}")

        def _apply_settings_controls(self) -> None:
            controls = (
                (self._open_browser_checkbox, "openBrowserOnStart"),
                (self._start_minimized_checkbox, "startMinimized"),
            )
            for control, key in controls:
                control.blockSignals(True)
                control.setChecked(
                    self._settings.value(key, bool(SETTING_DEFAULTS[key]), type=bool)
                )
                control.blockSignals(False)
            for key, control in self._notification_checkboxes.items():
                control.blockSignals(True)
                control.setChecked(
                    self._settings.value(key, bool(SETTING_DEFAULTS[key]), type=bool)
                )
                control.blockSignals(False)
            channel = str(self._settings.value("updateChannel", "Stable"))
            self._update_channel.blockSignals(True)
            self._update_channel.setCurrentText(
                channel if channel in {"Stable", "Pre-release"} else "Stable"
            )
            self._update_channel.blockSignals(False)
            selected_tab = self._settings.value("selectedTab", 0, type=int)
            self._tabs.setCurrentIndex(max(0, min(self._tabs.count() - 1, selected_tab)))

        def _import_settings(self) -> None:
            selected, _filter = QFileDialog.getOpenFileName(
                self,
                "Import DroidWebDisplay settings",
                str(self.controller.paths.downloads_root),
                "JSON files (*.json)",
            )
            if not selected:
                return
            try:
                imported = import_desktop_settings(self._settings, Path(selected))
            except Exception as exc:
                QMessageBox.warning(self, "DroidWebDisplay", f"Could not import settings:\n{exc}")
                return
            self._apply_settings_controls()
            QMessageBox.information(
                self,
                "DroidWebDisplay",
                f"Imported {len(imported)} desktop settings. Security sessions were not changed.",
            )

        def _reset_settings(self) -> None:
            answer = QMessageBox.question(
                self,
                "Reset desktop settings",
                "Reset desktop-host settings to defaults? Trusted sessions and authentication data will not be changed.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            reset_desktop_settings(self._settings)
            self._apply_settings_controls()
            QMessageBox.information(self, "DroidWebDisplay", "Desktop settings were reset to defaults.")

        def _check_for_updates(self) -> None:
            channel = self._update_channel.currentText()
            self._check_updates_button.setEnabled(False)
            self._update_status.setText(f"Checking {channel} releases…")

            def completed(result: object) -> None:
                self._check_updates_button.setEnabled(True)
                if not isinstance(result, ReleaseInfo):
                    self._update_status.setText("GitHub returned an unexpected release result.")
                    return
                self._latest_release_url = result.url
                self._open_release_button.setEnabled(True)
                release_type = "pre-release" if result.prerelease else "stable release"
                self._update_status.setText(
                    f"Current {__version__} · Latest {release_type}: {result.tag}"
                )

            def failed(message: str) -> None:
                self._check_updates_button.setEnabled(True)
                self._update_status.setText(f"Update check failed: {message}")

            self._start_support_task(
                lambda: check_latest_release(channel),
                on_ready=completed,
                on_failed=failed,
            )

        def _open_latest_release(self) -> None:
            if self._latest_release_url:
                QDesktopServices.openUrl(QUrl(self._latest_release_url))

        def _refresh_monitor(self) -> None:
            if self._monitor_running:
                return
            snapshot = self._last_snapshot
            self._monitor_running = True

            def task() -> object:
                resource = self._resource_monitor.sample(
                    server_url=snapshot.url,
                    uptime_seconds=snapshot.uptime_seconds,
                    adb_executable=Path(self.controller.paths.adb_executable),
                )
                timeline = read_timeline_events(self.controller.paths.logs_root, limit=40)
                return resource, timeline

            def completed(result: object) -> None:
                self._monitor_running = False
                if not isinstance(result, tuple) or len(result) != 2:
                    return
                resource, timeline = result
                if not isinstance(resource, ResourceSnapshot) or not isinstance(timeline, list):
                    return
                self._apply_resource_snapshot(resource, timeline)

            def failed(_message: str) -> None:
                self._monitor_running = False

            self._start_support_task(task, on_ready=completed, on_failed=failed)

        def _apply_resource_snapshot(
            self,
            resource: ResourceSnapshot,
            timeline: list[TimelineEvent],
        ) -> None:
            self._last_resource = resource
            self._metric_cpu.setText(f"{resource.cpu_percent:.1f}%")
            self._metric_ram.setText(format_bytes(resource.memory_bytes))
            self._metric_uptime.setText(_format_uptime(resource.uptime_seconds))
            self._metric_network.setText(
                f"↓ {format_bytes(resource.network_rx_per_second)}/s  "
                f"↑ {format_bytes(resource.network_tx_per_second)}/s"
            )
            self._metric_clients.setText(str(resource.client_count))
            self._metric_adb.setText(resource.adb_process_state)

            count = resource.client_count
            self._dashboard_clients.setText(f"{count} connected")
            if resource.client_hosts:
                self._dashboard_clients_detail.setText(" · ".join(resource.client_hosts))
            else:
                self._dashboard_clients_detail.setText("No active browser clients")
            connection = resource.android_connection or "Unknown"
            state = (
                "Connected"
                if resource.android_state == "device"
                else resource.android_state.title()
            )
            if self._device_is_connected(self._cached_device):
                self._dashboard_android_detail.setText(f"{connection} · {state}")
            elif resource.unauthorized_devices:
                self._dashboard_android_detail.setText("USB / ADB · Authorization required")
            else:
                self._dashboard_android_detail.setText("No connected Android device")

            current_clients = set(resource.client_hosts)
            if self._last_client_hosts is not None:
                for host in sorted(current_clients - self._last_client_hosts):
                    self._notify("notifyNewClient", f"New browser client connected: {host}")
            self._last_client_hosts = current_clients

            unauthorized = set(resource.unauthorized_devices)
            if self._last_unauthorized_devices is not None:
                for serial in sorted(unauthorized - self._last_unauthorized_devices):
                    self._notify(
                        "notifyUnauthorized",
                        f"Android device requires USB debugging authorization: {serial}",
                        warning=True,
                    )
                    self._record_runtime_event(
                        f"Android device {serial} requires authorization",
                        kind="android",
                    )
            self._last_unauthorized_devices = unauthorized

            if not self._timeline_seeded:
                self._seen_timeline_keys.update(event.key for event in timeline)
                self._timeline_seeded = True
            else:
                for event in timeline:
                    if event.key in self._seen_timeline_keys:
                        continue
                    self._seen_timeline_keys.add(event.key)
                    if event.kind == "transfer_failed":
                        self._notify("notifyTransferFailure", event.message, warning=True)
            self._seen_timeline_keys.intersection_update(
                {event.key for event in timeline}
                | {event.key for event in self._runtime_timeline}
            )
            self._refresh_timeline_display(timeline)

        '''
    )
    anchor = "    @property\n    def open_browser_on_start(self) -> bool:\n"
    if anchor not in gui:
        raise SystemExit("open_browser_on_start anchor missing")
    gui = gui.replace(anchor, support_methods + anchor, 1)

    snapshot_method = class_block(
        r'''
        def _apply_snapshot(self, snapshot: ServerSnapshot) -> None:
            previous_state = self._cached_state
            previous_device = self._cached_device
            self._last_snapshot = snapshot
            self._cached_state = snapshot.state
            labels = {
                ServerState.STOPPED: "Stopped",
                ServerState.STARTING: "Starting…",
                ServerState.RUNNING: "Running",
                ServerState.EXTERNAL: "Running · external",
                ServerState.STOPPING: "Stopping…",
                ServerState.ERROR: "Error",
            }
            self._set_status_visual(snapshot.state, labels[snapshot.state])
            self._diag_url.setText(snapshot.url)
            if snapshot.device:
                self._cached_device = snapshot.device
            device = self._cached_device

            self._dashboard_server.setText(labels[snapshot.state])
            port = QUrl(snapshot.url).port(8765)
            uptime = _format_uptime(snapshot.uptime_seconds) if snapshot.pid else "No process uptime"
            self._dashboard_server_detail.setText(f"{uptime} · port {port}")
            self._device_button.setText(device)
            network_label = {
                "local-only": "Local only",
                "lan-https": "LAN HTTPS",
            }.get(snapshot.network_mode, snapshot.network_mode.replace("-", " ").title())
            server_url = QUrl(snapshot.url)
            host = server_url.host() or "127.0.0.1"
            self._dashboard_network.setText(network_label)
            self._dashboard_network_detail.setText(host)
            self._error_value.setText(f"Last error: {snapshot.last_error or 'None'}")

            if self._notifications_initialized:
                if previous_state != ServerState.ERROR and snapshot.state == ServerState.ERROR:
                    self._notify(
                        "notifyServerFailure",
                        snapshot.last_error or "DroidWebDisplay server entered an error state.",
                        warning=True,
                    )
                if snapshot.device and previous_device != device:
                    was_connected = self._device_is_connected(previous_device)
                    is_connected = self._device_is_connected(device)
                    if is_connected and not was_connected:
                        self._notify("notifyAndroid", f"Android connected: {device}")
                        self._record_runtime_event(f"{device} connected", kind="android")
                    elif was_connected and not is_connected:
                        self._notify("notifyAndroid", f"Android disconnected: {previous_device}")
                        self._record_runtime_event(
                            f"{previous_device} disconnected",
                            kind="android",
                        )
            else:
                self._notifications_initialized = True

        '''
    )
    pattern = r"    def _apply_snapshot\(self, snapshot: ServerSnapshot\) -> None:\n.*?(?=        running = snapshot.state)"
    gui, count = re.subn(pattern, snapshot_method, gui, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"snapshot replacement count={count}")

    gui = replace_once(
        gui,
        "        if isinstance(snapshot, ServerSnapshot):\n            self._apply_snapshot(snapshot)\n",
        "        if isinstance(snapshot, ServerSnapshot):\n"
        "            self._apply_snapshot(snapshot)\n"
        "            if self._refresh_count % 2 == 1:\n"
        "                self._refresh_monitor()\n",
        "monitor refresh hook",
    )
    gui = replace_once(
        gui,
        "        self._set_health(self._health_server, \"error\", \"● Status unavailable\")\n",
        "        self._set_health(self._health_server, \"error\", \"● Status unavailable\")\n"
        "        if self._notifications_initialized:\n"
        "            self._notify(\"notifyServerFailure\", f\"Server status check failed: {message}\", warning=True)\n",
        "status failure notification",
    )

    GUI.write_text(gui, encoding="utf-8")


def patch_monitoring() -> None:
    monitoring = MONITORING.read_text(encoding="utf-8")
    monitoring = replace_once(
        monitoring,
        "    client_hosts: tuple[str, ...]\n"
        "    adb_process_state: str\n"
        "    unauthorized_devices: tuple[str, ...]\n",
        "    client_hosts: tuple[str, ...]\n"
        "    adb_process_state: str\n"
        "    android_connection: str\n"
        "    android_state: str\n"
        "    unauthorized_devices: tuple[str, ...]\n",
        "resource Android fields",
    )
    old = dedent(
        '''
            @staticmethod
            def _unauthorized_devices(adb_executable: Path) -> tuple[str, ...]:
                devices = _list_adb_devices(adb_executable)
                return tuple(
                    device.serial
                    for device in devices
                    if device.authorization_required
                )
        '''
    ).strip("\n")
    new = dedent(
        '''
            @staticmethod
            def _adb_inventory(adb_executable: Path) -> tuple[str, str, tuple[str, ...]]:
                devices = _list_adb_devices(adb_executable)
                unauthorized = tuple(
                    device.serial for device in devices if device.authorization_required
                )
                ready = next((device for device in devices if device.ready), None)
                if ready is not None:
                    return _connection_label(ready.connection_type), ready.state, unauthorized
                if devices:
                    first = devices[0]
                    return _connection_label(first.connection_type), first.state, unauthorized
                return "Unknown", "disconnected", unauthorized
        '''
    ).strip("\n")
    monitoring = replace_once(monitoring, old, new, "ADB inventory")
    monitoring = replace_once(
        monitoring,
        "        return ResourceSnapshot(\n            cpu_percent=cpu,\n",
        "        android_connection, android_state, unauthorized = self._adb_inventory(adb_executable)\n\n"
        "        return ResourceSnapshot(\n            cpu_percent=cpu,\n",
        "resource inventory call",
    )
    monitoring = replace_once(
        monitoring,
        "            client_hosts=self._client_hosts(server_url),\n"
        "            adb_process_state=self._adb_process_state(adb_executable),\n"
        "            unauthorized_devices=self._unauthorized_devices(adb_executable),\n",
        "            client_hosts=self._client_hosts(server_url),\n"
        "            adb_process_state=self._adb_process_state(adb_executable),\n"
        "            android_connection=android_connection,\n"
        "            android_state=android_state,\n"
        "            unauthorized_devices=unauthorized,\n",
        "resource inventory values",
    )
    old_display = dedent(
        '''
            def display_line(self) -> str:
                stamp = self.timestamp
                if "T" in stamp:
                    stamp = stamp.split("T", 1)[1]
                stamp = stamp.replace("Z", "")
                stamp = stamp[:5] if len(stamp) >= 5 else stamp
                return f"{stamp:>5}  {self.message}".rstrip()
        '''
    ).strip("\n")
    new_display = dedent(
        '''
            def display_line(self) -> str:
                stamp = self.timestamp
                try:
                    normalized = stamp.replace("Z", "+00:00")
                    parsed = datetime.fromisoformat(normalized)
                    if parsed.tzinfo is not None:
                        parsed = parsed.astimezone()
                    stamp = parsed.strftime("%H:%M")
                except ValueError:
                    if "T" in stamp:
                        stamp = stamp.split("T", 1)[1]
                    stamp = stamp.replace("Z", "")[:5]
                return f"{stamp:>5}  {self.message}".rstrip()
        '''
    ).strip("\n")
    monitoring = replace_once(monitoring, old_display, new_display, "timeline local timestamp")
    MONITORING.write_text(monitoring, encoding="utf-8")


def patch_theme() -> None:
    theme = THEME.read_text(encoding="utf-8")
    if "QLabel#dashboardValue" not in theme:
        css = dedent(
            '''
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

            '''
        )
        marker = "QLabel#healthStatus {{"
        if marker not in theme:
            raise SystemExit("health theme anchor missing")
        theme = theme.replace(marker, css + marker, 1)
    if "QPlainTextEdit#timelineView {{" not in theme:
        css = dedent(
            '''
            QPlainTextEdit#timelineView {{
                min-height: 118px;
                padding: 9px;
                font-family: "Cascadia Mono", "Consolas", "DejaVu Sans Mono", monospace;
                font-size: 9pt;
            }}

            '''
        )
        marker = "QMenu {{"
        if marker not in theme:
            raise SystemExit("menu theme anchor missing")
        theme = theme.replace(marker, css + marker, 1)
    THEME.write_text(theme, encoding="utf-8")


def patch_layout_tests() -> None:
    tests = LAYOUT_TEST.read_text(encoding="utf-8")
    marker = "def test_overview_has_dashboard_resources_timeline_and_device_details"
    if marker in tests:
        return
    tests += dedent(
        '''

        def test_overview_has_dashboard_resources_timeline_and_device_details() -> None:
            gui = (ROOT / "droid_web_display/desktop/gui.py").read_text(encoding="utf-8")
            assert 'card.setProperty("dashboardCard", True)' in gui
            assert '"Live event timeline"' in gui
            assert '"Network RX/TX"' in gui
            assert 'self._device_button.clicked.connect(self._show_android_details)' in gui


        def test_settings_expose_notifications_backup_and_update_controls() -> None:
            gui = (ROOT / "droid_web_display/desktop/gui.py").read_text(encoding="utf-8")
            assert '"Tray notifications"' in gui
            assert 'QPushButton("Export settings")' in gui
            assert 'QPushButton("Import settings")' in gui
            assert 'QPushButton("Reset defaults")' in gui
            assert 'QPushButton("Check for updates")' in gui
            assert 'self._update_channel.addItems(["Stable", "Pre-release"])' in gui
        '''
    )
    LAYOUT_TEST.write_text(tests, encoding="utf-8")


def main() -> None:
    patch_gui()
    patch_monitoring()
    patch_theme()
    patch_layout_tests()


if __name__ == "__main__":
    main()
