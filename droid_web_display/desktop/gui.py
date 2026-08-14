from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import signal
import sys
import tempfile
import uuid
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QSettings, QThreadPool, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from droid_web_display import __version__
from droid_web_display.desktop.controller import ServerController, ServerSnapshot, ServerState
from droid_web_display.desktop.monitoring import (
    AndroidDeviceDetails,
    ReleaseInfo,
    ResourceMonitor,
    ResourceSnapshot,
    TimelineEvent,
    check_latest_release,
    collect_android_device_details,
    format_bytes,
    read_timeline_events,
)
from droid_web_display.desktop.platform import StartupManager, open_directory
from droid_web_display.desktop.settings_backup import (
    SETTING_DEFAULTS,
    export_desktop_settings,
    import_desktop_settings,
    reset_desktop_settings,
)
from droid_web_display.desktop.support import (
    diagnostic_summary,
    export_diagnostics_bundle,
    read_log_entries,
)
from droid_web_display.desktop.theme import apply_desktop_theme

INSTANCE_NAME = "DroidWebDisplayDesktopHost-v1"
TAB_NAMES = ("Overview", "Health", "Logs", "Diagnostics", "Settings")


def _format_uptime(seconds: int) -> str:
    hours, remainder = divmod(max(0, seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:d}h {minutes:02d}m {seconds:02d}s"
    return f"{minutes:d}m {seconds:02d}s"


def _notify_existing_instance() -> bool:
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE_NAME)
    if not socket.waitForConnected(250):
        socket.abort()
        return False
    socket.write(b"activate\n")
    socket.flush()
    socket.waitForBytesWritten(250)
    socket.disconnectFromServer()
    return True


def _refresh_widget_style(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def _set_button_variant(button: QPushButton, variant: str | None) -> None:
    button.setProperty("variant", variant)
    _refresh_widget_style(button)


def _make_card(title: str, subtitle: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(11)
    heading = QLabel(title)
    heading.setObjectName("cardTitle")
    layout.addWidget(heading)
    if subtitle:
        hint = QLabel(subtitle)
        hint.setObjectName("sectionHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
    return card, layout


def _field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("fieldLabel", True)
    return label


def _field_value(text: str = "—", *, selectable: bool = False) -> QLabel:
    label = QLabel(text)
    label.setProperty("fieldValue", True)
    if selectable:
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return label


def _health_label(text: str = "Checking…", state: str = "idle") -> QLabel:
    label = QLabel(text)
    label.setObjectName("healthStatus")
    label.setProperty("healthState", state)
    label.setAlignment(Qt.AlignCenter)
    label.setMinimumWidth(150)
    return label


class _StatusSignals(QObject):
    ready = Signal(object)
    failed = Signal(str)


class _StatusProbe(QRunnable):
    def __init__(self, controller: ServerController, *, include_device: bool) -> None:
        super().__init__()
        self.controller = controller
        self.include_device = include_device
        self.signals = _StatusSignals()

    def run(self) -> None:
        try:
            snapshot = self.controller.snapshot(include_device=self.include_device)
        except Exception as exc:
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.signals.ready.emit(snapshot)


class _TaskSignals(QObject):
    ready = Signal(object)
    failed = Signal(str)


class _TaskWorker(QRunnable):
    def __init__(self, task: Callable[[], object]) -> None:
        super().__init__()
        self.task = task
        self.signals = _TaskSignals()

    def run(self) -> None:
        try:
            result = self.task()
        except Exception as exc:
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.signals.ready.emit(result)


class ServerWindow(QMainWindow):
    def __init__(
        self,
        controller: ServerController,
        startup: StartupManager,
        *,
        icon: QIcon,
        open_browser_on_start: bool,
    ) -> None:
        super().__init__()
        self.controller = controller
        self.startup = startup
        self.icon = icon
        self._exiting = False
        self._browser_pending = open_browser_on_start
        self._cached_device = "Checking…"
        self._cached_state = ServerState.STOPPED
        self._last_snapshot = ServerSnapshot(
            state=ServerState.STOPPED,
            url="http://127.0.0.1:8765/",
            network_mode="local-only",
            pid=None,
            uptime_seconds=0,
            device="",
            last_error=None,
        )
        self._refresh_count = 0
        self._status_probe_running = False
        self._status_worker: _StatusProbe | None = None
        self._support_workers: set[_TaskWorker] = set()
        self._thread_pool = QThreadPool.globalInstance()
        self._settings = QSettings("DroidWebDisplay", "DesktopHost")
        self._last_log_signature: tuple[object, ...] | None = None
        self._resource_monitor = ResourceMonitor()
        self._monitor_running = False
        self._last_resource: ResourceSnapshot | None = None
        self._last_client_hosts: set[str] | None = None
        self._last_unauthorized_devices: set[str] | None = None
        self._runtime_timeline: list[TimelineEvent] = []
        self._last_log_events: list[TimelineEvent] = []
        self._seen_timeline_keys: set[str] = set()
        self._timeline_seeded = False
        self._notifications_initialized = False
        self._latest_release_url = ""

        self.setWindowTitle("DroidWebDisplay Server")
        self.setWindowIcon(icon)
        self.setMinimumSize(640, 520)
        saved_geometry = self._settings.value("windowGeometryTabsV1")
        if saved_geometry is not None:
            self.restoreGeometry(saved_geometry)
        else:
            self.resize(760, 600)

        self._status_value = QLabel("Starting…")
        self._status_value.setObjectName("statusPill")
        self._status_value.setProperty("serverState", ServerState.STARTING.value)
        self._status_value.setAlignment(Qt.AlignCenter)
        self._status_value.setMinimumWidth(126)

        brand_title = QLabel("DroidWebDisplay")
        brand_title.setObjectName("brandTitle")
        brand_subtitle = QLabel("Desktop server manager")
        brand_subtitle.setObjectName("brandSubtitle")
        brand_layout = QVBoxLayout()
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(1)
        brand_layout.addWidget(brand_title)
        brand_layout.addWidget(brand_subtitle)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(2, 0, 2, 0)
        header_layout.setSpacing(12)
        header_layout.addLayout(brand_layout, 1)
        header_layout.addWidget(self._status_value, 0, Qt.AlignRight | Qt.AlignVCenter)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("mainTabs")
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(self._build_overview_tab(), "Overview")
        self._tabs.addTab(self._build_health_tab(), "Health")
        self._tabs.addTab(self._build_logs_tab(), "Logs")
        self._tabs.addTab(self._build_diagnostics_tab(), "Diagnostics")
        self._tabs.addTab(self._build_settings_tab(), "Settings")
        stored_tab = self._settings.value("selectedTab", 0, type=int)
        self._tabs.setCurrentIndex(max(0, min(self._tabs.count() - 1, stored_tab)))
        self._tabs.currentChanged.connect(self._tab_changed)

        self._footer_device = QLabel("● Checking Android device…")
        self._footer_device.setObjectName("footerDevice")
        self._footer_device.setProperty("deviceState", "idle")

        footer_open = QPushButton("Open DroidWebDisplay")
        footer_open.clicked.connect(self.controller.open_browser)
        _set_button_variant(footer_open, "primary")

        footer_exit = QPushButton("Exit")
        footer_exit.clicked.connect(self.request_exit)
        _set_button_variant(footer_exit, "danger")

        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 9, 0, 0)
        footer_layout.setSpacing(8)
        footer_layout.addWidget(self._footer_device, 1)
        footer_layout.addWidget(footer_open)
        footer_layout.addWidget(footer_exit)

        root = QWidget()
        root.setObjectName("serverRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        layout.addLayout(header_layout)
        layout.addWidget(self._tabs, 1)
        layout.addWidget(footer)
        self.setCentralWidget(root)

        self.tray: QSystemTrayIcon | None = None
        self._tray_start_stop_action: QAction | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._create_tray()

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

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

    def _build_health_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 10, 2, 2)
        layout.setSpacing(12)

        card, card_layout = _make_card(
            "System health",
            "Fast checks for the host, browser service, ADB connection, Android device and diagnostics.",
        )
        health_form = QFormLayout()
        health_form.setContentsMargins(0, 0, 0, 0)
        health_form.setHorizontalSpacing(28)
        health_form.setVerticalSpacing(10)
        health_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._health_server = _health_label()
        self._health_browser = _health_label()
        self._health_adb = _health_label()
        self._health_device = _health_label()
        self._health_logging = _health_label()

        for name, value in (
            ("Server", self._health_server),
            ("Browser UI", self._health_browser),
            ("ADB", self._health_adb),
            ("Android device", self._health_device),
            ("Diagnostics log", self._health_logging),
        ):
            health_form.addRow(_field_label(name), value)
        card_layout.addLayout(health_form)

        refresh_button = QPushButton("Run health check")
        refresh_button.clicked.connect(lambda: self._refresh(force=True))
        card_layout.addWidget(refresh_button, alignment=Qt.AlignLeft)

        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _build_logs_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 10, 2, 2)
        layout.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)

        self._log_source = QComboBox()
        self._log_source.addItems(["All", "Server", "Host"])
        self._log_source.setToolTip("Log source")
        self._log_level = QComboBox()
        self._log_level.addItems(["DEBUG", "INFO", "WARNING", "ERROR"])
        self._log_level.setCurrentText("INFO")
        self._log_level.setToolTip("Minimum severity")
        self._log_search = QLineEdit()
        self._log_search.setPlaceholderText("Search logs…")
        self._log_search.setClearButtonEnabled(True)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(lambda: self._refresh_logs(force=True))

        toolbar.addWidget(self._log_source)
        toolbar.addWidget(self._log_level)
        toolbar.addWidget(self._log_search, 1)
        toolbar.addWidget(refresh_button)

        self._log_view = QPlainTextEdit()
        self._log_view.setObjectName("logView")
        self._log_view.setReadOnly(True)
        self._log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._log_view.setPlaceholderText("Diagnostic log entries will appear here.")

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        copy_button = QPushButton("Copy Visible Log")
        copy_button.clicked.connect(self._copy_visible_log)
        open_button = QPushButton("Open Log Folder")
        open_button.clicked.connect(lambda: open_directory(self.controller.paths.logs_root))
        buttons.addWidget(copy_button)
        buttons.addWidget(open_button)
        buttons.addStretch(1)

        self._log_source.currentTextChanged.connect(lambda _text: self._refresh_logs(force=True))
        self._log_level.currentTextChanged.connect(lambda _text: self._refresh_logs(force=True))
        self._log_search.textChanged.connect(lambda _text: self._refresh_logs(force=True))

        layout.addLayout(toolbar)
        layout.addWidget(self._log_view, 1)
        layout.addLayout(buttons)
        return page

    def _build_diagnostics_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 10, 2, 2)
        layout.setSpacing(12)

        card, card_layout = _make_card(
            "Diagnostics",
            "Environment information is non-secret. Exported bundles contain sanitized logs and metadata only.",
        )
        self._diag_version = _field_value(__version__, selectable=True)
        self._diag_os = _field_value(platform.platform(), selectable=True)
        self._diag_arch = _field_value(platform.machine() or "Unknown")
        self._diag_python = _field_value(platform.python_version())
        self._diag_pid = _field_value(str(os.getpid()))
        self._diag_url = _field_value(selectable=True)
        self._diag_adb = _field_value(str(self.controller.paths.adb_executable), selectable=True)
        self._diag_logs = _field_value(str(self.controller.paths.logs_root), selectable=True)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(28)
        form.setVerticalSpacing(8)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        for name, value in (
            ("DroidWebDisplay", self._diag_version),
            ("Operating system", self._diag_os),
            ("Architecture", self._diag_arch),
            ("Python", self._diag_python),
            ("Desktop PID", self._diag_pid),
            ("Server URL", self._diag_url),
            ("ADB", self._diag_adb),
            ("Logs", self._diag_logs),
        ):
            form.addRow(_field_label(name), value)
        card_layout.addLayout(form)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        copy_button = QPushButton("Copy Diagnostic Summary")
        copy_button.clicked.connect(self._copy_diagnostic_summary)
        self._export_button = QPushButton("Export Diagnostics ZIP")
        self._export_button.clicked.connect(self._export_diagnostics)
        _set_button_variant(self._export_button, "primary")
        actions.addWidget(copy_button)
        actions.addWidget(self._export_button)
        actions.addStretch(1)
        card_layout.addLayout(actions)

        self._export_status = QLabel("")
        self._export_status.setObjectName("sectionHint")
        self._export_status.setWordWrap(True)
        card_layout.addWidget(self._export_status)

        layout.addWidget(card)
        layout.addStretch(1)
        return page

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

    @property
    def open_browser_on_start(self) -> bool:
        return self._open_browser_checkbox.isChecked()

    @property
    def start_minimized_preference(self) -> bool:
        return self._start_minimized_checkbox.isChecked()

    def _tab_changed(self, index: int) -> None:
        self._settings.setValue("selectedTab", index)
        if self._tabs.tabText(index) == "Logs":
            self._refresh_logs(force=True)

    def _set_status_visual(self, state: ServerState, text: str) -> None:
        self._status_value.setText(text)
        self._status_value.setProperty("serverState", state.value)
        _refresh_widget_style(self._status_value)

    def _set_health(self, label: QLabel, state: str, text: str) -> None:
        label.setText(text)
        label.setProperty("healthState", state)
        _refresh_widget_style(label)

    def _create_tray(self) -> None:
        tray = QSystemTrayIcon(self.icon, self)
        menu = QMenu(self)
        open_action = QAction("Open DroidWebDisplay", self)
        open_action.triggered.connect(self.controller.open_browser)
        show_action = QAction("Show Server Manager", self)
        show_action.triggered.connect(self.activate_from_peer)
        self._tray_start_stop_action = QAction("Stop Server", self)
        self._tray_start_stop_action.triggered.connect(self._toggle_server)
        restart_action = QAction("Restart Server", self)
        restart_action.triggered.connect(self._restart_server)
        logs_action = QAction("Open Logs", self)
        logs_action.triggered.connect(lambda: open_directory(self.controller.paths.logs_root))
        exit_action = QAction("Exit DroidWebDisplay", self)
        exit_action.triggered.connect(self.request_exit)
        menu.addAction(open_action)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(self._tray_start_stop_action)
        menu.addAction(restart_action)
        menu.addAction(logs_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        tray.setContextMenu(menu)
        tray.setToolTip("DroidWebDisplay — Starting")
        tray.activated.connect(self._tray_activated)
        tray.show()
        self.tray = tray

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.activate_from_peer()

    def activate_from_peer(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        if self._cached_state in {ServerState.RUNNING, ServerState.EXTERNAL}:
            self.controller.open_browser()

    def _set_autostart(self, enabled: bool) -> None:
        try:
            self.startup.set_enabled(enabled)
        except Exception as exc:
            self._startup_checkbox.blockSignals(True)
            self._startup_checkbox.setChecked(not enabled)
            self._startup_checkbox.blockSignals(False)
            QMessageBox.warning(self, "DroidWebDisplay", f"Could not update startup settings:\n{exc}")

    def _toggle_server(self) -> None:
        state = self._cached_state
        if state in {ServerState.RUNNING, ServerState.STARTING}:
            self._set_status_visual(ServerState.STOPPING, "Stopping…")
            if not self.controller.stop():
                QMessageBox.warning(
                    self,
                    "DroidWebDisplay",
                    "The server did not stop within the expected timeout.",
                )
        elif state == ServerState.EXTERNAL:
            QMessageBox.information(
                self,
                "DroidWebDisplay",
                "A DroidWebDisplay server started outside this desktop host is already using this URL. "
                "Stop that instance separately.",
            )
        else:
            self._set_status_visual(ServerState.STARTING, "Starting…")
            self.controller.start()
            if self.open_browser_on_start:
                self._browser_pending = True
        self._refresh(force=True)

    def _restart_server(self) -> None:
        if self._cached_state == ServerState.EXTERNAL:
            QMessageBox.information(
                self,
                "DroidWebDisplay",
                "The running server is owned by another process and cannot be restarted from this "
                "desktop host.",
            )
            return
        self._set_status_visual(ServerState.STARTING, "Restarting…")
        if not self.controller.restart():
            QMessageBox.warning(self, "DroidWebDisplay", "The server could not be restarted cleanly.")
            return
        self._browser_pending = False
        self._refresh(force=True)

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

        running = snapshot.state in {ServerState.RUNNING, ServerState.STARTING}
        external = snapshot.state == ServerState.EXTERNAL
        action_text = "Stop Server" if running else "Start Server"
        self._start_stop_button.setText(action_text)
        self._start_stop_button.setEnabled(not external and snapshot.state != ServerState.STOPPING)
        _set_button_variant(self._start_stop_button, "danger" if running else "primary")
        if self._tray_start_stop_action is not None:
            self._tray_start_stop_action.setText(action_text)
            self._tray_start_stop_action.setEnabled(not external and snapshot.state != ServerState.STOPPING)

        server_ok = snapshot.state in {ServerState.RUNNING, ServerState.EXTERNAL}
        if server_ok:
            self._set_health(self._health_server, "ok", "● Healthy")
            self._set_health(self._health_browser, "ok", "● Reachable")
        elif snapshot.state in {ServerState.STARTING, ServerState.STOPPING}:
            self._set_health(self._health_server, "warn", f"● {labels[snapshot.state]}")
            self._set_health(self._health_browser, "warn", "● Waiting")
        elif snapshot.state == ServerState.ERROR:
            self._set_health(self._health_server, "error", "● Error")
            self._set_health(self._health_browser, "error", "● Unavailable")
        else:
            self._set_health(self._health_server, "idle", "● Stopped")
            self._set_health(self._health_browser, "idle", "● Offline")

        device = self._cached_device
        if device == "ADB unavailable":
            self._set_health(self._health_adb, "error", "● Unavailable")
            self._set_health(self._health_device, "idle", "● No device")
            footer_state = "error"
            footer_text = "● ADB unavailable"
        elif device in {"No device", "Checking…", "—"}:
            self._set_health(self._health_adb, "ok" if device == "No device" else "warn", "● Ready" if device == "No device" else "● Checking")
            self._set_health(self._health_device, "idle", "● No device" if device == "No device" else "● Checking")
            footer_state = "idle"
            footer_text = "● No Android device" if device == "No device" else "● Checking Android device…"
        else:
            self._set_health(self._health_adb, "ok", "● Connected")
            self._set_health(self._health_device, "ok", f"● {device}")
            footer_state = "ok"
            footer_text = f"● {device}"

        self._footer_device.setText(footer_text)
        self._footer_device.setProperty("deviceState", footer_state)
        _refresh_widget_style(self._footer_device)

        log_path = self.controller.paths.logs_root / "server.log"
        if log_path.is_file():
            self._set_health(self._health_logging, "ok", "● Active")
        elif server_ok:
            self._set_health(self._health_logging, "warn", "● Awaiting data")
        else:
            self._set_health(self._health_logging, "idle", "● Idle")

        if self.tray is not None:
            self.tray.setToolTip(f"DroidWebDisplay — {labels[snapshot.state]} — {device}")

        if self._browser_pending and snapshot.state in {ServerState.RUNNING, ServerState.EXTERNAL}:
            self._browser_pending = False
            self.controller.open_browser()

        if self._tabs.currentIndex() == 2:
            self._refresh_logs()

    def _status_ready(self, snapshot: object) -> None:
        self._status_probe_running = False
        self._status_worker = None
        if isinstance(snapshot, ServerSnapshot):
            self._apply_snapshot(snapshot)
            if self._refresh_count % 2 == 1:
                self._refresh_monitor()

    def _status_failed(self, message: str) -> None:
        self._status_probe_running = False
        self._status_worker = None
        self._set_status_visual(ServerState.ERROR, "Status unavailable")
        self._error_value.setText(message)
        self._set_health(self._health_server, "error", "● Status unavailable")
        if self._notifications_initialized:
            self._notify("notifyServerFailure", f"Server status check failed: {message}", warning=True)

    def _refresh(self, *, force: bool = False) -> None:
        if self._status_probe_running:
            return
        self._refresh_count += 1
        include_device = force or self._refresh_count % 3 == 1
        worker = _StatusProbe(self.controller, include_device=include_device)
        worker.signals.ready.connect(self._status_ready)
        worker.signals.failed.connect(self._status_failed)
        self._status_worker = worker
        self._status_probe_running = True
        self._thread_pool.start(worker)

    def _log_file_signature(self) -> tuple[object, ...]:
        values: list[object] = [
            self._log_source.currentText(),
            self._log_level.currentText(),
            self._log_search.text(),
        ]
        for name in ("server.log", "desktop-host.log"):
            path = self.controller.paths.logs_root / name
            try:
                stat = path.stat()
                values.extend((stat.st_size, stat.st_mtime_ns))
            except OSError:
                values.extend((0, 0))
        return tuple(values)

    def _refresh_logs(self, *, force: bool = False) -> None:
        signature = self._log_file_signature()
        if not force and signature == self._last_log_signature:
            return
        self._last_log_signature = signature
        entries = read_log_entries(
            self.controller.paths.logs_root,
            source=self._log_source.currentText(),
            minimum_level=self._log_level.currentText(),
            search=self._log_search.text(),
        )
        text = "\n".join(entry.display_line() for entry in entries)
        scrollbar = self._log_view.verticalScrollBar()
        was_at_bottom = scrollbar.value() >= max(0, scrollbar.maximum() - 4)
        self._log_view.setPlainText(text)
        if was_at_bottom or force:
            scrollbar.setValue(scrollbar.maximum())

    def _copy_visible_log(self) -> None:
        QApplication.clipboard().setText(self._log_view.toPlainText())

    def _start_support_task(
        self,
        task: Callable[[], object],
        *,
        on_ready: Callable[[object], None],
        on_failed: Callable[[str], None] | None = None,
    ) -> None:
        worker = _TaskWorker(task)
        self._support_workers.add(worker)

        def ready(result: object) -> None:
            self._support_workers.discard(worker)
            on_ready(result)

        def failed(message: str) -> None:
            self._support_workers.discard(worker)
            if on_failed is not None:
                on_failed(message)
            else:
                QMessageBox.warning(self, "DroidWebDisplay", message)

        worker.signals.ready.connect(ready)
        worker.signals.failed.connect(failed)
        self._thread_pool.start(worker)

    def _copy_diagnostic_summary(self) -> None:
        snapshot = self._last_snapshot

        def completed(result: object) -> None:
            QApplication.clipboard().setText(str(result))
            self._export_status.setText("Diagnostic summary copied to the clipboard.")

        self._start_support_task(
            lambda: diagnostic_summary(self.controller.paths, snapshot),
            on_ready=completed,
        )

    def _export_diagnostics(self) -> None:
        snapshot = self._last_snapshot
        self._export_button.setEnabled(False)
        self._export_status.setText("Creating sanitized diagnostic bundle…")

        def completed(result: object) -> None:
            self._export_button.setEnabled(True)
            target = Path(str(result))
            self._export_status.setText(f"Saved: {target}")
            QMessageBox.information(
                self,
                "DroidWebDisplay",
                f"Diagnostic bundle created:\n{target}",
            )

        def failed(message: str) -> None:
            self._export_button.setEnabled(True)
            self._export_status.setText("Diagnostic export failed.")
            QMessageBox.warning(self, "DroidWebDisplay", f"Could not export diagnostics:\n{message}")

        self._start_support_task(
            lambda: export_diagnostics_bundle(self.controller.paths, snapshot),
            on_ready=completed,
            on_failed=failed,
        )

    def request_exit(self) -> None:
        self._settings.setValue("windowGeometryTabsV1", self.saveGeometry())
        self._exiting = True
        QApplication.instance().quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._settings.setValue("windowGeometryTabsV1", self.saveGeometry())
        if self._exiting:
            event.accept()
            return
        if self.tray is not None and self.tray.isVisible():
            self.hide()
        else:
            self.showMinimized()
        event.ignore()


def run_desktop_app(
    controller: ServerController,
    startup: StartupManager,
    *,
    icon_path: Path,
    start_minimized: bool = False,
    open_browser: bool = True,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("DroidWebDisplay")
    app.setOrganizationName("DroidWebDisplay")
    app.setQuitOnLastWindowClosed(False)
    apply_desktop_theme(app)

    if _notify_existing_instance():
        return 0

    QLocalServer.removeServer(INSTANCE_NAME)
    instance_server = QLocalServer()
    if not instance_server.listen(INSTANCE_NAME):
        raise RuntimeError(
            "Could not create the DroidWebDisplay single-instance socket: "
            f"{instance_server.errorString()}"
        )

    icon = QIcon(str(icon_path))
    if icon.isNull():
        icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    app.setWindowIcon(icon)

    window = ServerWindow(controller, startup, icon=icon, open_browser_on_start=open_browser)

    def activate_pending_connections() -> None:
        while instance_server.hasPendingConnections():
            socket = instance_server.nextPendingConnection()
            if socket is None:
                continue
            socket.waitForReadyRead(100)
            socket.readAll()
            socket.disconnectFromServer()
            window.activate_from_peer()

    instance_server.newConnection.connect(activate_pending_connections)

    cleanup_done = False

    def cleanup() -> None:
        nonlocal cleanup_done
        if cleanup_done:
            return
        cleanup_done = True
        instance_server.close()
        if window.tray is not None:
            window.tray.hide()
        if not controller.stop(timeout=10.0):
            controller.force_cleanup_children()

    app.aboutToQuit.connect(cleanup)

    def request_quit(*_args: object) -> None:
        QTimer.singleShot(0, app.quit)

    for signal_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signal_name, None)
        if sig is not None:
            try:
                signal.signal(sig, request_quit)
            except (OSError, ValueError):
                pass

    controller.start()
    stored_minimized = window.start_minimized_preference
    if start_minimized or stored_minimized:
        if window.tray is not None:
            window.hide()
        else:
            window.showMinimized()
    else:
        window.show()

    QTimer.singleShot(100, lambda: window._refresh(force=True))
    result = app.exec()
    cleanup()
    return int(result)


def desktop_smoke_test(icon_path: Path) -> int:
    if (
        sys.platform.startswith("linux")
        and not os.environ.get("DISPLAY")
        and not os.environ.get("WAYLAND_DISPLAY")
    ):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(["DroidWebDisplay-desktop-smoke"])
    app.setApplicationName("DroidWebDisplay")
    apply_desktop_theme(app)
    icon = QIcon(str(icon_path))

    with tempfile.TemporaryDirectory(prefix="dwd-desktop-smoke-") as temporary:
        root = Path(temporary)

        class _SmokePaths:
            logs_root = root
            downloads_root = root
            state_root = root
            data_root = root
            adb_executable = "adb"

        class _SmokeController:
            paths = _SmokePaths()

            def snapshot(self, *, include_device: bool = True) -> ServerSnapshot:
                return ServerSnapshot(
                    state=ServerState.STOPPED,
                    url="http://127.0.0.1:8765/",
                    network_mode="local-only",
                    pid=None,
                    uptime_seconds=0,
                    device="No device" if include_device else "",
                    last_error=None,
                )

            def open_browser(self) -> bool:
                return True

            def start(self) -> bool:
                return True

            def stop(self, timeout: float = 10.0) -> bool:
                return True

            def restart(self, timeout: float = 10.0) -> bool:
                return True

            def force_cleanup_children(self) -> None:
                return None

        class _SmokeStartup:
            supported = False

            def enabled(self) -> bool:
                return False

            def set_enabled(self, enabled: bool) -> None:
                return None

        window = ServerWindow(
            _SmokeController(),  # type: ignore[arg-type]
            _SmokeStartup(),  # type: ignore[arg-type]
            icon=icon,
            open_browser_on_start=False,
        )
        window._timer.stop()
        QThreadPool.globalInstance().waitForDone(1000)
        app.processEvents()
        tabs = tuple(window._tabs.tabText(index) for index in range(window._tabs.count()))
        ok = tabs == TAB_NAMES
        window._exiting = True
        window.close()
        app.processEvents()
        return 0 if ok else 3
