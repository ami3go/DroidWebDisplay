from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import psutil

from droid_web_display.adb.devices import parse_adb_devices
from droid_web_display.diagnostics import redact_text


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_percent: float
    memory_bytes: int
    uptime_seconds: int
    network_rx_per_second: float
    network_tx_per_second: float
    client_hosts: tuple[str, ...]
    adb_process_state: str
    unauthorized_devices: tuple[str, ...]

    @property
    def client_count(self) -> int:
        return len(self.client_hosts)


@dataclass(frozen=True)
class AndroidDeviceDetails:
    model: str
    manufacturer: str
    serial: str
    android_version: str
    api_level: str
    screen_resolution: str
    battery_percent: str
    connection_type: str
    adb_state: str
    physical_display_id: str
    available_ram: str

    def summary_text(self) -> str:
        fields = (
            ("Model", self.model),
            ("Manufacturer", self.manufacturer),
            ("Serial", self.serial),
            ("Android", self.android_version),
            ("API level", self.api_level),
            ("Screen resolution", self.screen_resolution),
            ("Battery", self.battery_percent),
            ("Connection", self.connection_type),
            ("ADB state", self.adb_state),
            ("Physical display ID", self.physical_display_id),
            ("Available RAM", self.available_ram),
        )
        return "\n".join(f"{label}: {value}" for label, value in fields)


@dataclass(frozen=True)
class TimelineEvent:
    key: str
    timestamp: str
    message: str
    kind: str = "info"

    def display_line(self) -> str:
        stamp = self.timestamp
        if "T" in stamp:
            stamp = stamp.split("T", 1)[1]
        stamp = stamp.replace("Z", "")
        stamp = stamp[:5] if len(stamp) >= 5 else stamp
        return f"{stamp:>5}  {self.message}".rstrip()


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    name: str
    url: str
    prerelease: bool


class ResourceMonitor:
    """Collect lightweight desktop-host metrics without touching the video/session path."""

    def __init__(self) -> None:
        self._process = psutil.Process(os.getpid())
        self._process.cpu_percent(None)
        counters = psutil.net_io_counters()
        self._last_net = (counters.bytes_recv, counters.bytes_sent)
        self._last_net_at = time.monotonic()

    @staticmethod
    def _connection_host(address: object) -> str | None:
        if not address:
            return None
        host = getattr(address, "ip", None)
        if host:
            return str(host)
        if isinstance(address, tuple) and address:
            return str(address[0])
        return None

    @staticmethod
    def _connection_port(address: object) -> int | None:
        if not address:
            return None
        port = getattr(address, "port", None)
        if port is not None:
            return int(port)
        if isinstance(address, tuple) and len(address) > 1:
            return int(address[1])
        return None

    def _client_hosts(self, server_url: str) -> tuple[str, ...]:
        try:
            port = urlsplit(server_url).port
        except ValueError:
            port = None
        if port is None:
            return ()
        try:
            connections = self._process.net_connections(kind="tcp")
        except (psutil.AccessDenied, psutil.Error, OSError):
            return ()
        hosts: set[str] = set()
        for connection in connections:
            if connection.status != psutil.CONN_ESTABLISHED:
                continue
            if self._connection_port(connection.laddr) != port:
                continue
            host = self._connection_host(connection.raddr)
            if host:
                hosts.add(host)
        return tuple(sorted(hosts))

    @staticmethod
    def _adb_process_state(adb_executable: Path) -> str:
        if not adb_executable.exists():
            return "Unavailable"
        expected = adb_executable.stem.casefold()
        try:
            for process in psutil.process_iter(["name", "exe"]):
                name = str(process.info.get("name") or "").casefold()
                executable = str(process.info.get("exe") or "")
                stem = Path(executable).stem.casefold() if executable else ""
                if name.removesuffix(".exe") == expected or stem == expected:
                    return "Running"
        except (psutil.AccessDenied, psutil.Error, OSError):
            return "Unknown"
        return "Idle"

    @staticmethod
    def _unauthorized_devices(adb_executable: Path) -> tuple[str, ...]:
        devices = _list_adb_devices(adb_executable)
        return tuple(
            device.serial
            for device in devices
            if device.authorization_required
        )

    def sample(
        self,
        *,
        server_url: str,
        uptime_seconds: int,
        adb_executable: Path,
    ) -> ResourceSnapshot:
        now = time.monotonic()
        counters = psutil.net_io_counters()
        elapsed = max(0.001, now - self._last_net_at)
        previous_rx, previous_tx = self._last_net
        rx_rate = max(0.0, (counters.bytes_recv - previous_rx) / elapsed)
        tx_rate = max(0.0, (counters.bytes_sent - previous_tx) / elapsed)
        self._last_net = (counters.bytes_recv, counters.bytes_sent)
        self._last_net_at = now

        try:
            cpu = max(0.0, self._process.cpu_percent(None))
            memory = max(0, int(self._process.memory_info().rss))
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            cpu = 0.0
            memory = 0

        return ResourceSnapshot(
            cpu_percent=cpu,
            memory_bytes=memory,
            uptime_seconds=max(0, int(uptime_seconds)),
            network_rx_per_second=rx_rate,
            network_tx_per_second=tx_rate,
            client_hosts=self._client_hosts(server_url),
            adb_process_state=self._adb_process_state(adb_executable),
            unauthorized_devices=self._unauthorized_devices(adb_executable),
        )


def _run_command(command: list[str], *, timeout: float = 3.0) -> subprocess.CompletedProcess[str] | None:
    kwargs: dict[str, object] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(command, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return None


def _list_adb_devices(adb_executable: Path):  # type: ignore[no-untyped-def]
    result = _run_command([str(adb_executable), "devices", "-l"])
    if result is None or result.returncode != 0:
        return []
    return parse_adb_devices(result.stdout)


def _adb_shell(adb_executable: Path, serial: str, *arguments: str) -> str:
    result = _run_command([str(adb_executable), "-s", serial, "shell", *arguments])
    if result is None or result.returncode != 0:
        return ""
    return result.stdout.strip()


def _first_property(adb_executable: Path, serial: str, name: str, fallback: str) -> str:
    value = _adb_shell(adb_executable, serial, "getprop", name).strip()
    return value or fallback


def _screen_size(text: str) -> str:
    matches = re.findall(r"(?:Physical|Override) size:\s*(\d+x\d+)", text, flags=re.IGNORECASE)
    return matches[-1] if matches else "Unknown"


def _battery_level(text: str) -> str:
    match = re.search(r"(?m)^\s*level:\s*(\d+)", text)
    return f"{match.group(1)}%" if match else "Unknown"


def _display_id(text: str) -> str:
    for pattern in (
        r"\bmDisplayId=(\d+)",
        r"\bdisplayId=(\d+)",
        r"\bDisplay\s+(\d+)\b",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return "0" if text else "Unknown"


def _available_ram(text: str) -> str:
    match = re.search(r"(?m)^MemAvailable:\s*(\d+)\s*kB", text)
    if not match:
        return "Unknown"
    value = int(match.group(1)) * 1024
    return format_bytes(value)


def _connection_label(connection_type: str) -> str:
    labels = {
        "usb": "USB",
        "tcpip": "Wi-Fi / TCP-IP",
        "emulator": "Emulator",
        "unknown": "Unknown",
    }
    return labels.get(connection_type, connection_type or "Unknown")


def collect_android_device_details(adb_executable: Path) -> AndroidDeviceDetails | None:
    devices = _list_adb_devices(adb_executable)
    if not devices:
        return None
    device = next((candidate for candidate in devices if candidate.ready), devices[0])
    fallback_model = device.model or "Unknown"
    if not device.ready:
        return AndroidDeviceDetails(
            model=fallback_model,
            manufacturer="Unknown",
            serial=device.serial,
            android_version="Unavailable",
            api_level="Unavailable",
            screen_resolution="Unavailable",
            battery_percent="Unavailable",
            connection_type=_connection_label(device.connection_type),
            adb_state=device.state,
            physical_display_id="Unavailable",
            available_ram="Unavailable",
        )

    serial = device.serial
    model = _first_property(adb_executable, serial, "ro.product.model", fallback_model)
    manufacturer = _first_property(adb_executable, serial, "ro.product.manufacturer", "Unknown")
    android_version = _first_property(adb_executable, serial, "ro.build.version.release", "Unknown")
    api_level = _first_property(adb_executable, serial, "ro.build.version.sdk", "Unknown")
    resolution = _screen_size(_adb_shell(adb_executable, serial, "wm", "size"))
    battery = _battery_level(_adb_shell(adb_executable, serial, "dumpsys", "battery"))
    physical_display = _display_id(_adb_shell(adb_executable, serial, "dumpsys", "display"))
    available_ram = _available_ram(_adb_shell(adb_executable, serial, "cat", "/proc/meminfo"))
    return AndroidDeviceDetails(
        model=model,
        manufacturer=manufacturer,
        serial=serial,
        android_version=android_version,
        api_level=api_level,
        screen_resolution=resolution,
        battery_percent=battery,
        connection_type=_connection_label(device.connection_type),
        adb_state=device.state,
        physical_display_id=physical_display,
        available_ram=available_ram,
    )


def _tail_server_json(log_path: Path, *, maximum_bytes: int = 512 * 1024) -> list[dict[str, object]]:
    if not log_path.is_file():
        return []
    try:
        size = log_path.stat().st_size
        with log_path.open("rb") as handle:
            if size > maximum_bytes:
                handle.seek(size - maximum_bytes)
                handle.readline()
            raw = handle.read(maximum_bytes)
    except OSError:
        return []
    records: list[dict[str, object]] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _human_timeline_event(payload: dict[str, object]) -> tuple[str, str] | None:
    event = str(payload.get("event") or "")
    message = redact_text(str(payload.get("message") or "")).strip()
    client = redact_text(str(payload.get("client") or "")).strip()
    lowered = f"{event} {message}".casefold()

    if event == "logging.configured":
        return "server", "Server started"
    if event == "websocket.connect":
        return "browser_connected", f"Browser {client or 'client'} connected"
    if event == "websocket.close":
        return "browser_disconnected", f"Browser {client or 'client'} disconnected"
    if event == "websocket.exception":
        return "browser_error", f"Browser {client or 'client'} connection failed"
    if "transfer" in lowered and any(word in lowered for word in ("fail", "error", "exception")):
        return "transfer_failed", f"Transfer failed: {message or event}"
    if "display" in lowered and any(word in lowered for word in ("created", "started", "launch", "running")):
        return "display", message or event.replace(".", " ").capitalize()
    if event in {"server.started", "server.ready"}:
        return "server", message or "Server started"
    if event in {"server.stopped", "server.shutdown"}:
        return "server", message or "Server stopped"
    if any(word in event.casefold() for word in ("session.started", "session.connected")):
        return "session", message or event.replace(".", " ").capitalize()
    return None


def read_timeline_events(logs_root: Path, *, limit: int = 40) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    for payload in _tail_server_json(logs_root / "server.log"):
        human = _human_timeline_event(payload)
        if human is None:
            continue
        kind, message = human
        timestamp = str(payload.get("timestamp") or "")
        key = "|".join(
            (
                timestamp,
                str(payload.get("event") or ""),
                str(payload.get("request_id") or ""),
                message,
            )
        )
        events.append(TimelineEvent(key=key, timestamp=timestamp, message=message, kind=kind))
    return events[-max(1, limit):]


def format_bytes(value: float | int) -> str:
    number = max(0.0, float(value))
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if number < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{number:.0f} {unit}"
            return f"{number:.1f} {unit}"
        number /= 1024.0
    return f"{number:.1f} TiB"


def check_latest_release(channel: str, *, timeout: float = 5.0) -> ReleaseInfo:
    request = Request(
        "https://api.github.com/repos/ami3go/DroidWebDisplay/releases?per_page=10",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "DroidWebDisplay"},
    )
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed HTTPS GitHub endpoint
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("GitHub returned an unexpected release response")
    allow_prerelease = channel.casefold() == "pre-release"
    for item in payload:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        prerelease = bool(item.get("prerelease"))
        if prerelease and not allow_prerelease:
            continue
        tag = str(item.get("tag_name") or "").strip()
        url = str(item.get("html_url") or "").strip()
        if not tag or not url:
            continue
        return ReleaseInfo(
            tag=tag,
            name=str(item.get("name") or tag),
            url=url,
            prerelease=prerelease,
        )
    raise RuntimeError(f"No {channel} release was found")
