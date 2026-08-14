from __future__ import annotations

import os
from pathlib import Path
import signal
import sys
import uuid

from PySide6.QtCore import QObject, QRunnable, QSettings, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from droid_web_display.desktop.controller import ServerController, ServerSnapshot, ServerState
from droid_web_display.desktop.platform import StartupManager, open_directory

INSTANCE_NAME = "DroidWebDisplayDesktopHost-v1"


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
        self._refresh_count = 0
        self._status_probe_running = False
        self._status_worker: _StatusProbe | None = None
        self._thread_pool = QThreadPool.globalInstance()
        self._settings = QSettings("DroidWebDisplay", "DesktopHost")

        self.setWindowTitle("DroidWebDisplay Server")
        self.setWindowIcon(icon)
        self.resize(560, 430)
        self.setMinimumSize(500, 390)

        self._status_value = QLabel("Starting")
        self._url_value = QLabel("—")
        self._url_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._network_value = QLabel("—")
        self._device_value = QLabel("—")
        self._pid_value = QLabel("—")
        self._uptime_value = QLabel("—")
        self._error_value = QLabel("None")
        self._error_value.setWordWrap(True)

        status_box = QGroupBox("Status")
        status_form = QFormLayout(status_box)
        status_form.addRow("Server", self._status_value)
        status_form.addRow("URL", self._url_value)
        status_form.addRow("Network mode", self._network_value)
        status_form.addRow("Android device", self._device_value)
        status_form.addRow("Process", self._pid_value)
        status_form.addRow("Uptime", self._uptime_value)
        status_form.addRow("Last error", self._error_value)

        self._start_stop_button = QPushButton("Stop Server")
        self._start_stop_button.clicked.connect(self._toggle_server)
        open_button = QPushButton("Open DroidWebDisplay")
        open_button.clicked.connect(self.controller.open_browser)
        restart_button = QPushButton("Restart Server")
        restart_button.clicked.connect(self._restart_server)
        logs_button = QPushButton("Open Logs")
        logs_button.clicked.connect(lambda: open_directory(self.controller.paths.logs_root))

        controls = QGroupBox("Server")
        controls_layout = QHBoxLayout(controls)
        controls_layout.addWidget(open_button)
        controls_layout.addWidget(self._start_stop_button)
        controls_layout.addWidget(restart_button)
        controls_layout.addWidget(logs_button)

        self._open_browser_checkbox = QCheckBox("Open browser when DroidWebDisplay starts")
        self._open_browser_checkbox.setChecked(
            self._settings.value("openBrowserOnStart", True, type=bool)
        )
        self._open_browser_checkbox.toggled.connect(
            lambda checked: self._settings.setValue("openBrowserOnStart", checked)
        )

        self._startup_checkbox = QCheckBox("Start DroidWebDisplay when I sign in")
        self._startup_checkbox.setEnabled(startup.supported)
        if startup.supported:
            self._startup_checkbox.setChecked(startup.enabled())
        self._startup_checkbox.toggled.connect(self._set_autostart)

        self._start_minimized_checkbox = QCheckBox("Start desktop host minimized")
        self._start_minimized_checkbox.setChecked(
            self._settings.value("startMinimized", False, type=bool)
        )
        self._start_minimized_checkbox.toggled.connect(
            lambda checked: self._settings.setValue("startMinimized", checked)
        )

        settings_box = QGroupBox("Desktop host")
        settings_layout = QVBoxLayout(settings_box)
        settings_layout.addWidget(self._open_browser_checkbox)
        settings_layout.addWidget(self._startup_checkbox)
        settings_layout.addWidget(self._start_minimized_checkbox)
        settings_layout.addWidget(
            QLabel(
                "Closing the browser does not stop DroidWebDisplay. Use Exit from this window "
                "or the tray menu to stop it cleanly."
            )
        )

        exit_button = QPushButton("Exit DroidWebDisplay")
        exit_button.clicked.connect(self.request_exit)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(status_box)
        layout.addWidget(controls)
        layout.addWidget(settings_box)
        layout.addStretch(1)
        layout.addWidget(exit_button, alignment=Qt.AlignRight)
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

    @property
    def open_browser_on_start(self) -> bool:
        return self._open_browser_checkbox.isChecked()

    @property
    def start_minimized_preference(self) -> bool:
        return self._start_minimized_checkbox.isChecked()

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
            self._status_value.setText("Stopping…")
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
            self._status_value.setText("Starting…")
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
        self._status_value.setText("Restarting…")
        if not self.controller.restart():
            QMessageBox.warning(self, "DroidWebDisplay", "The server could not be restarted cleanly.")
            return
        self._browser_pending = False
        self._refresh(force=True)

    def _apply_snapshot(self, snapshot: ServerSnapshot) -> None:
        self._cached_state = snapshot.state
        labels = {
            ServerState.STOPPED: "Stopped",
            ServerState.STARTING: "Starting…",
            ServerState.RUNNING: "Running",
            ServerState.EXTERNAL: "Running (external instance)",
            ServerState.STOPPING: "Stopping…",
            ServerState.ERROR: "Error",
        }
        self._status_value.setText(labels[snapshot.state])
        self._url_value.setText(snapshot.url)
        self._network_value.setText(snapshot.network_mode)
        if snapshot.device:
            self._cached_device = snapshot.device
        self._device_value.setText(self._cached_device)
        self._pid_value.setText(str(snapshot.pid) if snapshot.pid else "—")
        self._uptime_value.setText(_format_uptime(snapshot.uptime_seconds) if snapshot.pid else "—")
        self._error_value.setText(snapshot.last_error or "None")

        running = snapshot.state in {ServerState.RUNNING, ServerState.STARTING}
        external = snapshot.state == ServerState.EXTERNAL
        action_text = "Stop Server" if running else "Start Server"
        self._start_stop_button.setText(action_text)
        self._start_stop_button.setEnabled(not external and snapshot.state != ServerState.STOPPING)
        if self._tray_start_stop_action is not None:
            self._tray_start_stop_action.setText(action_text)
            self._tray_start_stop_action.setEnabled(not external and snapshot.state != ServerState.STOPPING)
        if self.tray is not None:
            self.tray.setToolTip(f"DroidWebDisplay — {labels[snapshot.state]} — {self._cached_device}")

        if self._browser_pending and snapshot.state in {ServerState.RUNNING, ServerState.EXTERNAL}:
            self._browser_pending = False
            self.controller.open_browser()

    def _status_ready(self, snapshot: object) -> None:
        self._status_probe_running = False
        self._status_worker = None
        if isinstance(snapshot, ServerSnapshot):
            self._apply_snapshot(snapshot)

    def _status_failed(self, message: str) -> None:
        self._status_probe_running = False
        self._status_worker = None
        self._error_value.setText(message)

    def _refresh(self, *, force: bool = False) -> None:
        if self._status_probe_running and not force:
            return
        if self._status_probe_running:
            return
        self._refresh_count += 1
        include_device = self._refresh_count % 3 == 1
        worker = _StatusProbe(self.controller, include_device=include_device)
        worker.signals.ready.connect(self._status_ready)
        worker.signals.failed.connect(self._status_failed)
        self._status_worker = worker
        self._status_probe_running = True
        self._thread_pool.start(worker)

    def request_exit(self) -> None:
        self._exiting = True
        QApplication.instance().quit()

    def closeEvent(self, event: QCloseEvent) -> None:
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
    icon = QIcon(str(icon_path))
    test_server = QLocalServer()
    name = f"DroidWebDisplayDesktopSmoke-{uuid.uuid4().hex}"
    QLocalServer.removeServer(name)
    if not test_server.listen(name):
        return 2
    widget = QWidget()
    widget.setWindowIcon(icon)
    widget.setWindowTitle("DroidWebDisplay Server")
    widget.close()
    test_server.close()
    QLocalServer.removeServer(name)
    app.processEvents()
    return 0
