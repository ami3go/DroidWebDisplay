from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path
import ssl
import subprocess
import sys
import threading
import time
from typing import Callable, Protocol
import urllib.error
import urllib.request
import webbrowser

import psutil

from droid_web_display.adb.devices import parse_adb_devices
from droid_web_display.network_access import LAN_HTTPS, NetworkConfigStore

PRODUCT_TITLE_MARKER = "<title>DroidWebDisplay</title>"
WEB_UI_MARKER = "droidwebdisplay-native-single-drawer-v1"


class RuntimeHandle(Protocol):
    @property
    def shutdown_requested(self) -> bool: ...

    def request_shutdown(self) -> None: ...


ServerRunner = Callable[[list[str] | None, RuntimeHandle | None], int]
RuntimeFactory = Callable[[], RuntimeHandle]


class ServerState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    EXTERNAL = "external"
    STOPPING = "stopping"
    ERROR = "error"


@dataclass(frozen=True)
class DesktopPaths:
    resource_root: Path
    state_root: Path
    data_root: Path
    downloads_root: Path
    logs_root: Path
    adb_executable: Path | str

    @classmethod
    def from_resource_root(cls, resource_root: Path) -> "DesktopPaths":
        resource_root = resource_root.resolve()
        if os.name == "nt":
            base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
            state_root = base / "DroidWebDisplay"
        else:
            base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
            state_root = base / "droidwebdisplay"

        downloads_base = Path.home() / "Downloads"
        if not downloads_base.exists():
            downloads_base = state_root / "downloads"

        data_root = state_root / "data"
        logs_root = state_root / "logs"
        downloads_root = downloads_base / "DroidWebDisplay"
        for path in (state_root, data_root, logs_root, downloads_root):
            path.mkdir(parents=True, exist_ok=True)

        adb_name = "adb.exe" if os.name == "nt" else "adb"
        bundled_adb = resource_root / "adb" / adb_name
        adb: Path | str = bundled_adb if bundled_adb.is_file() else adb_name
        return cls(resource_root, state_root, data_root, downloads_root, logs_root, adb)

    @property
    def network_config(self) -> Path:
        return self.data_root / "network-access.json"

    def server_arguments(self, extra: list[str] | None = None) -> list[str]:
        return [
            "--repo-root",
            str(self.resource_root),
            "--data-directory",
            str(self.data_root),
            "--download-directory",
            str(self.downloads_root),
            "--network-config",
            str(self.network_config),
            "--log-directory",
            str(self.logs_root),
            "--adb",
            str(self.adb_executable),
            *(extra or []),
        ]


@dataclass(frozen=True)
class ServerSnapshot:
    state: ServerState
    url: str
    network_mode: str
    pid: int | None
    uptime_seconds: int
    device: str
    last_error: str | None


class ServerController:
    def __init__(
        self,
        paths: DesktopPaths,
        *,
        server_runner: ServerRunner,
        runtime_factory: RuntimeFactory,
        server_args: list[str] | None = None,
    ) -> None:
        self.paths = paths
        self._server_runner = server_runner
        self._runtime_factory = runtime_factory
        self._server_args = list(server_args or [])
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._runtime: RuntimeHandle | None = None
        self._state = ServerState.STOPPED
        self._last_error: str | None = None
        self._started_at: float | None = None

    def _arg_value(self, name: str) -> str | None:
        result: str | None = None
        for index, value in enumerate(self._server_args[:-1]):
            if value == name:
                result = self._server_args[index + 1]
        return result

    def _network_details(self) -> tuple[str, str]:
        host_override = self._arg_value("--host")
        port_override = self._arg_value("--port")
        try:
            network = NetworkConfigStore(self.paths.network_config).load()
            network_mode = network.mode
            scheme = "https" if network.mode == LAN_HTTPS else "http"
            host = host_override or network.hostname or network.bind_address
            port = int(port_override) if port_override else network.port
        except Exception:
            network_mode = "local-only"
            scheme = "http"
            host = host_override or "127.0.0.1"
            port = int(port_override) if port_override else 8765
        if host in {"0.0.0.0", "::", ""}:
            host = "127.0.0.1"
        return network_mode, f"{scheme}://{host}:{port}/"

    @staticmethod
    def _probe(url: str) -> bool:
        context = None
        if url.lower().startswith("https://"):
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        request = urllib.request.Request(url, headers={"User-Agent": "DroidWebDisplay-desktop-host/1"})
        try:
            with urllib.request.urlopen(request, timeout=0.35, context=context) as response:
                html = response.read(512 * 1024).decode("utf-8", errors="replace")
            return PRODUCT_TITLE_MARKER in html and WEB_UI_MARKER in html
        except (urllib.error.URLError, OSError, ValueError):
            return False

    def _run_server(self, runtime: RuntimeHandle) -> None:
        try:
            return_code = self._server_runner(
                self.paths.server_arguments(["--no-browser", *self._server_args]),
                runtime,
            )
        except BaseException as exc:  # keep the desktop host alive when the worker fails
            with self._lock:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._state = ServerState.ERROR
            return
        with self._lock:
            if self._state == ServerState.STOPPING or runtime.shutdown_requested:
                self._state = ServerState.STOPPED
            elif return_code == 0:
                self._state = ServerState.STOPPED
            else:
                self._last_error = f"Server exited with code {return_code}"
                self._state = ServerState.ERROR

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            runtime = self._runtime_factory()
            self._runtime = runtime
            self._state = ServerState.STARTING
            self._last_error = None
            self._started_at = time.monotonic()
            self._thread = threading.Thread(
                target=self._run_server,
                args=(runtime,),
                name="DroidWebDisplayServer",
                daemon=True,
            )
            self._thread.start()
            return True

    def stop(self, timeout: float = 10.0) -> bool:
        with self._lock:
            thread = self._thread
            runtime = self._runtime
            if thread is None or not thread.is_alive():
                self._state = ServerState.STOPPED
                return True
            self._state = ServerState.STOPPING
            if runtime is not None:
                runtime.request_shutdown()
        thread.join(timeout=max(0.0, timeout))
        with self._lock:
            stopped = not thread.is_alive()
            if stopped:
                self._state = ServerState.STOPPED
                self._thread = None
                self._runtime = None
            else:
                # Surface the failure as ERROR rather than leaving the machine
                # parked in STOPPING, which the UI treats as "busy" and would
                # never leave on its own.
                self._state = ServerState.ERROR
                self._last_error = "Timed out while stopping the embedded server"
            return stopped

    def restart(self, timeout: float = 10.0) -> bool:
        if not self.stop(timeout=timeout):
            return False
        return self.start()

    def open_browser(self) -> bool:
        _, url = self._network_details()
        return bool(webbrowser.open(url))

    def _device_summary(self) -> str:
        command = [str(self.paths.adb_executable), "devices", "-l"]
        kwargs: dict[str, object] = {
            "capture_output": True,
            "text": True,
            "timeout": 1.25,
            "check": False,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(command, **kwargs)
        except (OSError, subprocess.SubprocessError):
            return "ADB unavailable"
        if result.returncode != 0:
            return "ADB unavailable"

        ready_devices = [device for device in parse_adb_devices(result.stdout) if device.ready]
        if not ready_devices:
            return "No device"
        if len(ready_devices) == 1:
            device = ready_devices[0]
            return device.model or device.serial
        return f"{len(ready_devices)} devices"

    def snapshot(self, *, include_device: bool = True) -> ServerSnapshot:
        network_mode, url = self._network_details()
        current_ui = self._probe(url)
        with self._lock:
            thread_alive = bool(self._thread and self._thread.is_alive())
            if current_ui:
                self._state = ServerState.RUNNING if thread_alive else ServerState.EXTERNAL
            elif thread_alive:
                if self._state not in {ServerState.ERROR, ServerState.STOPPING}:
                    self._state = ServerState.STARTING
            elif self._state != ServerState.ERROR:
                # Nothing owned is running and nothing answers the probe, so a
                # previously observed external server is gone too.
                self._state = ServerState.STOPPED
            uptime = int(time.monotonic() - self._started_at) if self._started_at and thread_alive else 0
            state = self._state
            error = self._last_error
        return ServerSnapshot(
            state=state,
            url=url,
            network_mode=network_mode,
            pid=os.getpid() if thread_alive else None,
            uptime_seconds=max(0, uptime),
            device=self._device_summary() if include_device else "",
            last_error=error,
        )

    def force_cleanup_children(self) -> None:
        try:
            children = psutil.Process(os.getpid()).children(recursive=True)
        except psutil.Error:
            return
        for process in children:
            try:
                process.terminate()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(children, timeout=2.0)
        for process in alive:
            try:
                process.kill()
            except psutil.Error:
                pass
