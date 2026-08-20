from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

from droid_web_display import __version__
from droid_web_display.process_utils import subprocess_creation_kwargs
from droid_web_display.desktop.controller import DesktopPaths, ServerSnapshot
from droid_web_display.diagnostics import redact_text


@dataclass(frozen=True)
class LogEntry:
    source: str
    level: str
    timestamp: str
    message: str
    event: str = ""

    def display_line(self) -> str:
        stamp = self.timestamp
        if "T" in stamp:
            stamp = stamp.split("T", 1)[1].replace("Z", "")
        if len(stamp) > 12:
            stamp = stamp[:12]
        prefix = f"{stamp:>12}  {self.level:<7}  {self.source:<6}"
        event = f"  {self.event}" if self.event else ""
        return f"{prefix}{event}  {self.message}".rstrip()


def _tail_text_lines(
    path: Path,
    *,
    maximum_bytes: int = 256 * 1024,
    maximum_lines: int = 700,
) -> list[str]:
    if not path.is_file():
        return []
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > maximum_bytes:
                handle.seek(max(0, size - maximum_bytes))
                handle.readline()
            raw = handle.read(maximum_bytes)
    except OSError:
        return []
    lines = raw.decode("utf-8", errors="replace").splitlines()
    return lines[-maximum_lines:]


def _server_entries(path: Path) -> list[LogEntry]:
    entries: list[LogEntry] = []
    for raw in _tail_text_lines(path):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            entries.append(LogEntry("Server", "INFO", "", redact_text(raw)))
            continue
        if not isinstance(payload, dict):
            continue
        entries.append(
            LogEntry(
                source="Server",
                level=str(payload.get("level") or "INFO").upper(),
                timestamp=str(payload.get("timestamp") or ""),
                message=redact_text(str(payload.get("message") or "")),
                event=str(payload.get("event") or ""),
            )
        )
    return entries


def _host_entries(path: Path) -> list[LogEntry]:
    return [
        LogEntry("Host", "INFO", "", redact_text(raw))
        for raw in _tail_text_lines(path)
        if raw.strip()
    ]


def read_log_entries(
    logs_root: Path,
    *,
    source: str = "All",
    minimum_level: str = "DEBUG",
    search: str = "",
    limit: int = 400,
) -> list[LogEntry]:
    """Read a bounded recent view of the server and desktop-host logs."""

    level_order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    threshold = level_order.get(minimum_level.upper(), 10)
    entries: list[LogEntry] = []
    if source in {"All", "Server"}:
        entries.extend(_server_entries(logs_root / "server.log"))
    if source in {"All", "Host"}:
        entries.extend(_host_entries(logs_root / "desktop-host.log"))

    needle = search.casefold().strip()
    filtered = [
        entry
        for entry in entries
        if level_order.get(entry.level.upper(), 20) >= threshold
        and (
            not needle
            or needle in entry.message.casefold()
            or needle in entry.event.casefold()
            or needle in entry.source.casefold()
        )
    ]
    return filtered[-max(1, limit):]


def _run_version(command: list[str]) -> str:
    kwargs: dict[str, object] = {
        "capture_output": True,
        "text": True,
        "timeout": 2.0,
        "check": False,
    }
    kwargs.update(subprocess_creation_kwargs())
    try:
        result = subprocess.run(command, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return "Unavailable"
    output = (result.stdout or result.stderr or "").strip().splitlines()
    return redact_text(output[0]) if output else "Unavailable"


def diagnostic_environment(paths: DesktopPaths, snapshot: ServerSnapshot) -> dict[str, object]:
    """Return non-secret environment data suitable for display and support bundles."""

    return {
        "droidwebdisplay_version": __version__,
        "platform": platform.platform(),
        "operating_system": platform.system(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "executable": str(Path(sys.executable).name),
        "process_id": os.getpid(),
        "server_state": snapshot.state.value,
        "server_url": snapshot.url,
        "network_mode": snapshot.network_mode,
        "server_pid": snapshot.pid,
        "server_uptime_seconds": snapshot.uptime_seconds,
        "android_device": snapshot.device,
        "last_error": redact_text(snapshot.last_error or "None"),
        "adb": _run_version([str(paths.adb_executable), "version"]),
        "adb_executable": str(paths.adb_executable),
        "state_directory": str(paths.state_root),
        "data_directory": str(paths.data_root),
        "downloads_directory": str(paths.downloads_root),
        "logs_directory": str(paths.logs_root),
        "log_level": os.environ.get("DWD_LOG_LEVEL", "INFO").upper(),
        "log_rotation": "server.log: 5 MiB × 5 backups; desktop-host.log: 2 MiB × 3 backups",
    }


def diagnostic_summary(paths: DesktopPaths, snapshot: ServerSnapshot) -> str:
    data = diagnostic_environment(paths, snapshot)
    labels = (
        ("DroidWebDisplay", "droidwebdisplay_version"),
        ("Operating system", "platform"),
        ("Architecture", "architecture"),
        ("Python", "python"),
        ("Process", "process_id"),
        ("Server state", "server_state"),
        ("Server URL", "server_url"),
        ("Network mode", "network_mode"),
        ("Android device", "android_device"),
        ("ADB", "adb"),
        ("Log level", "log_level"),
        ("Logs", "logs_directory"),
        ("Last error", "last_error"),
    )
    return "\n".join(f"{label}: {data[key]}" for label, key in labels)


def _sanitized_log_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(redact_text(line) for line in text.splitlines()) + ("\n" if text else "")


def export_diagnostics_bundle(
    paths: DesktopPaths,
    snapshot: ServerSnapshot,
    *,
    destination_directory: Path | None = None,
) -> Path:
    """Create a support ZIP containing only sanitized logs and non-secret metadata."""

    destination_directory = (destination_directory or paths.downloads_root).resolve()
    destination_directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = destination_directory / f"DroidWebDisplay-diagnostics-{stamp}.zip"
    metadata = diagnostic_environment(paths, snapshot)

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "diagnostics.json",
            json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        archive.writestr("diagnostic-summary.txt", diagnostic_summary(paths, snapshot) + "\n")
        archive.writestr(
            "README.txt",
            "DroidWebDisplay diagnostic bundle.\n"
            "Authentication secrets, request query strings, and file contents are intentionally excluded.\n",
        )
        for pattern in ("server.log*", "desktop-host.log*"):
            for log_path in sorted(paths.logs_root.glob(pattern)):
                if not log_path.is_file():
                    continue
                archive.writestr(
                    f"logs/{log_path.name}",
                    _sanitized_log_text(log_path),
                )
    return target
