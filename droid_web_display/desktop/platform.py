from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading
from typing import TextIO

_LOG_HANDLE: TextIO | None = None
_LOG_LOCK = threading.RLock()


class _Tee:
    def __init__(self, original: TextIO | None, log: TextIO) -> None:
        self._original = original
        self._log = log

    def write(self, value: str) -> int:
        with _LOG_LOCK:
            if self._original is not None:
                try:
                    self._original.write(value)
                    self._original.flush()
                except OSError:
                    pass
            self._log.write(value)
            self._log.flush()
        return len(value)

    def flush(self) -> None:
        with _LOG_LOCK:
            if self._original is not None:
                try:
                    self._original.flush()
                except OSError:
                    pass
            self._log.flush()

    def isatty(self) -> bool:
        return bool(self._original and getattr(self._original, "isatty", lambda: False)())

    @property
    def encoding(self) -> str:
        return getattr(self._original, "encoding", None) or "utf-8"


def install_output_logging(logs_root: Path, *, maximum_bytes: int = 2 * 1024 * 1024) -> Path:
    global _LOG_HANDLE
    logs_root.mkdir(parents=True, exist_ok=True)
    log_path = logs_root / "desktop-host.log"
    if log_path.is_file() and log_path.stat().st_size >= maximum_bytes:
        for index in range(3, 0, -1):
            source = logs_root / ("desktop-host.log" if index == 1 else f"desktop-host.log.{index - 1}")
            destination = logs_root / f"desktop-host.log.{index}"
            if source.exists():
                destination.unlink(missing_ok=True)
                source.replace(destination)
    _LOG_HANDLE = log_path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = _Tee(sys.stdout, _LOG_HANDLE)  # type: ignore[assignment]
    sys.stderr = _Tee(sys.stderr, _LOG_HANDLE)  # type: ignore[assignment]
    return log_path


def application_command(resource_root: Path, *, start_minimized: bool = False) -> list[str]:
    if getattr(sys, "frozen", False):
        executable = os.environ.get("APPIMAGE") if sys.platform.startswith("linux") else None
        command = [executable or sys.executable]
    else:
        command = [sys.executable, str(resource_root / "tools" / "desktop_entry.py")]
    if start_minimized:
        command.append("--start-minimized")
    return command


def _windows_command_line(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def _desktop_exec(command: list[str]) -> str:
    def quote(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
        return f'"{escaped}"'

    return " ".join(quote(value) for value in command)


class StartupManager:
    def __init__(self, resource_root: Path) -> None:
        self.resource_root = resource_root.resolve()

    @property
    def supported(self) -> bool:
        return os.name == "nt" or sys.platform.startswith("linux")

    @property
    def _linux_path(self) -> Path:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
        return config_home / "autostart" / "droidwebdisplay.desktop"

    def enabled(self) -> bool:
        if os.name == "nt":
            try:
                import winreg

                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Run",
                ) as key:
                    winreg.QueryValueEx(key, "DroidWebDisplay")
                return True
            except (FileNotFoundError, OSError):
                return False
        if sys.platform.startswith("linux"):
            return self._linux_path.is_file()
        return False

    def set_enabled(self, enabled: bool) -> None:
        if os.name == "nt":
            import winreg

            path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, path) as key:
                if enabled:
                    winreg.SetValueEx(
                        key,
                        "DroidWebDisplay",
                        0,
                        winreg.REG_SZ,
                        _windows_command_line(application_command(self.resource_root, start_minimized=True)),
                    )
                else:
                    try:
                        winreg.DeleteValue(key, "DroidWebDisplay")
                    except FileNotFoundError:
                        pass
            return
        if sys.platform.startswith("linux"):
            path = self._linux_path
            if enabled:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    "\n".join(
                        [
                            "[Desktop Entry]",
                            "Type=Application",
                            "Name=DroidWebDisplay",
                            "Comment=Start the DroidWebDisplay desktop host",
                            "Exec="
                            + _desktop_exec(
                                application_command(self.resource_root, start_minimized=True)
                            ),
                            "Terminal=false",
                            "X-GNOME-Autostart-enabled=true",
                            "Categories=Utility;Development;",
                            "",
                        ]
                    ),
                    encoding="utf-8",
                )
            else:
                path.unlink(missing_ok=True)
            return
        raise RuntimeError("Desktop autostart is not supported on this platform")


def open_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
        return
    subprocess.Popen(["xdg-open", str(path)])


def command_preview(resource_root: Path) -> str:
    command = application_command(resource_root, start_minimized=True)
    return _windows_command_line(command) if os.name == "nt" else shlex.join(command)
