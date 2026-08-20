from __future__ import annotations

import asyncio
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from droid_web_display.process_utils import subprocess_creation_kwargs
from droid_web_display.errors import AdbCommandError, AdbUnavailableError
from droid_web_display.models import AndroidDevice

from .devices import parse_adb_devices
from .running_apps import RunningGuiApp, parse_running_gui_apps, validate_component_name
from .storage_metrics import collect_storage_metadata


async def _terminate(process: asyncio.subprocess.Process) -> None:
    """Kill and reap a child, shielded so cancellation cannot abandon it."""
    if process.returncode is not None:
        return
    try:
        # ProcessLookupError (already reaped) is an OSError subclass.
        process.kill()
    except OSError:
        pass
    try:
        await asyncio.shield(process.wait())
    except asyncio.CancelledError:
        pass


def _subprocess_creation_kwargs(platform_name: str | None = None) -> dict[str, int]:
    """Return platform-specific flags for invisible background child processes."""
    return subprocess_creation_kwargs(platform_name)


@dataclass(frozen=True)
class AdbCommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class SpawnedAdbProcess(Protocol):
    returncode: int | None
    stdout: asyncio.StreamReader | None
    stderr: asyncio.StreamReader | None

    async def wait(self) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


class AdbBackend(Protocol):
    async def list_devices(self, *, enrich: bool = False) -> list[AndroidDevice]: ...

    async def get_state(self, serial: str) -> str: ...

    async def push(self, serial: str, local: Path, remote: str) -> None: ...

    async def create_forward(self, serial: str, local_port: int, socket_name: str) -> None: ...

    async def remove_forward(self, serial: str, local_port: int) -> None: ...

    async def spawn_server(self, serial: str, server_args: Sequence[str]) -> SpawnedAdbProcess: ...


class AdbClient:
    def __init__(
        self,
        executable: str | os.PathLike[str] = "adb",
        *,
        command_timeout: float = 20.0,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.executable = os.fspath(executable)
        self.command_timeout = command_timeout
        self.environment = dict(environment or {})

    def resolved_executable(self) -> str:
        path = Path(self.executable)
        if path.is_file():
            return str(path)
        resolved = shutil.which(self.executable)
        if not resolved:
            raise AdbUnavailableError(
                f"ADB executable not found: {self.executable}",
                details={"executable": self.executable},
            )
        return resolved

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(self.environment)
        return env

    async def run(
        self,
        *args: str,
        timeout: float | None = None,
        check: bool = True,
    ) -> AdbCommandResult:
        executable = self.resolved_executable()
        argv = (executable, *args)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env(),
                **_subprocess_creation_kwargs(),
            )
        except OSError as exc:
            raise AdbUnavailableError(
                f"Unable to start ADB: {exc}",
                details={"executable": executable},
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self.command_timeout if timeout is None else timeout,
            )
        except asyncio.TimeoutError as exc:
            await _terminate(process)
            raise AdbCommandError(
                f"ADB command timed out: {' '.join(argv)}",
                details={"argv": list(argv), "timeout": timeout or self.command_timeout},
            ) from exc
        except OSError as exc:
            # A pipe failure part-way through a command still means ADB is
            # unusable, and callers only handle the bridge error type.
            await _terminate(process)
            raise AdbUnavailableError(
                f"Unable to communicate with ADB: {exc}",
                details={"executable": executable},
            ) from exc
        except BaseException:
            # Cancellation (and any other failure while waiting) must still reap
            # the child, otherwise aborted requests leak adb processes.
            await _terminate(process)
            raise

        result = AdbCommandResult(
            argv=argv,
            returncode=process.returncode or 0,
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
        )
        if check and result.returncode != 0:
            raise AdbCommandError(
                f"ADB command returned {result.returncode}: {' '.join(argv)}",
                details={
                    "argv": list(argv),
                    "returncode": result.returncode,
                    "stdout": result.stdout[-4000:],
                    "stderr": result.stderr[-4000:],
                },
            )
        return result

    async def version(self) -> str:
        result = await self.run("version")
        return (result.stdout or result.stderr).strip()

    async def list_devices(self, *, enrich: bool = False) -> list[AndroidDevice]:
        result = await self.run("devices", "-l")
        devices = parse_adb_devices(result.stdout)
        if not enrich:
            return devices

        enriched: list[AndroidDevice] = []
        for device in devices:
            if not device.ready:
                enriched.append(device)
                continue
            properties = await self.get_properties(
                device.serial,
                (
                    "ro.product.manufacturer",
                    "ro.product.model",
                    "ro.build.version.release",
                    "ro.build.version.sdk",
                ),
            )
            storage_metadata = await collect_storage_metadata(self, device.serial)
            sdk_value = properties.get("ro.build.version.sdk")
            try:
                sdk = int(sdk_value) if sdk_value else None
            except ValueError:
                sdk = None
            enriched.append(
                AndroidDevice(
                    serial=device.serial,
                    state=device.state,
                    model=properties.get("ro.product.model") or device.model,
                    product=device.product,
                    device=device.device,
                    transport_id=device.transport_id,
                    usb=device.usb,
                    manufacturer=properties.get("ro.product.manufacturer"),
                    android_version=properties.get("ro.build.version.release"),
                    sdk=sdk,
                    connection_type=device.connection_type,
                    metadata={**device.metadata, **storage_metadata},
                )
            )
        return enriched

    async def get_properties(self, serial: str, names: Sequence[str]) -> dict[str, str]:
        values: dict[str, str] = {}
        for name in names:
            result = await self.run("-s", serial, "shell", "getprop", name, check=False)
            if result.returncode == 0:
                value = result.stdout.strip()
                if value:
                    values[name] = value
        return values


    async def shell(self, serial: str, *args: str, check: bool = True, timeout: float | None = None) -> AdbCommandResult:
        return await self.run("-s", serial, "shell", *args, check=check, timeout=timeout)

    async def external_storage_roots(self, serial: str) -> list[dict[str, str]]:
        result = await self.shell(serial, "ls", "-1", "/storage", check=False, timeout=20.0)
        if result.returncode != 0:
            return []
        roots: list[dict[str, str]] = []
        for raw in result.stdout.splitlines():
            volume = raw.strip()
            if not re.fullmatch(r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}", volume):
                continue
            path = f"/storage/{volume}"
            check = await self.shell(serial, "test", "-d", path, check=False, timeout=10.0)
            if check.returncode == 0:
                roots.append({"id": f"sd-card-{volume.lower()}", "label": f"SD card · {volume}", "path": path})
        return roots

    async def package_installed(self, serial: str, package_name: str) -> bool:
        result = await self.shell(serial, "pm", "path", package_name, check=False, timeout=20.0)
        return result.returncode == 0 and any(line.startswith("package:") for line in result.stdout.splitlines())

    async def list_launchable_apps(self, serial: str) -> list[dict[str, str]]:
        result = await self.shell(
            serial,
            "cmd",
            "package",
            "query-activities",
            "--brief",
            "--components",
            "-a",
            "android.intent.action.MAIN",
            "-c",
            "android.intent.category.LAUNCHER",
            check=False,
            timeout=30.0,
        )
        packages: set[str] = set()
        for raw in result.stdout.splitlines():
            line = raw.strip()
            if not line or "/" not in line or line.startswith("No activities"):
                continue
            package = line.split("/", 1)[0]
            if package and all(ch.isalnum() or ch in "._" for ch in package):
                packages.add(package)
        apps = []
        for package in sorted(packages):
            if package == "com.openai.chatgpt":
                label = "ChatGPT"
            else:
                label = package.rsplit(".", 1)[-1].replace("_", " ").title()
            apps.append({"label": label, "packageName": package})
        return apps


    async def free_memory_bytes(self, serial: str) -> int | None:
        result = await self.shell(serial, "cat", "/proc/meminfo", check=False, timeout=10.0)
        if result.returncode != 0:
            return None
        for raw in result.stdout.splitlines():
            match = re.match(r"^MemAvailable:\s+(\d+)\s+kB$", raw.strip(), re.IGNORECASE)
            if match:
                return int(match.group(1)) * 1024
        return None

    async def list_running_gui_apps(self, serial: str) -> list[RunningGuiApp]:
        result = await self.shell(serial, "dumpsys", "activity", "activities", check=False, timeout=30.0)
        if result.returncode != 0:
            raise AdbCommandError(
                "Unable to query running Android applications",
                details={"serial": serial, "stderr": result.stderr[-2000:]},
            )
        return parse_running_gui_apps(result.stdout)

    async def move_running_app_to_display(
        self,
        serial: str,
        *,
        task_id: int,
        component_name: str,
        display_id: int,
    ) -> dict[str, object]:
        if task_id <= 0:
            raise ValueError("Android task ID must be positive")
        if display_id <= 0:
            raise ValueError("Virtual display ID must be positive")
        component = validate_component_name(component_name)

        # Android's supported shell surface exposes --display for activity
        # launch. --activity-reorder-to-front requests reuse of the existing
        # activity/task where Android permits it. Some applications may create
        # a second task or reject secondary-display launch; the API reports the
        # post-command verification result instead of claiming a guaranteed move.
        result = await self.shell(
            serial,
            "am",
            "start",
            "--display",
            str(display_id),
            "--activity-reorder-to-front",
            "-n",
            component,
            check=False,
            timeout=30.0,
        )
        combined = (result.stdout + "\n" + result.stderr).strip()
        lowered = combined.lower()
        failed = result.returncode != 0 or "error:" in lowered or "exception" in lowered
        if failed:
            raise AdbCommandError(
                "Android rejected moving the application to the virtual display",
                details={
                    "serial": serial,
                    "taskId": task_id,
                    "componentName": component,
                    "displayId": display_id,
                    "returncode": result.returncode,
                    "output": combined[-3000:],
                },
            )
        return {
            "strategy": "start-activity-on-display",
            "taskId": task_id,
            "componentName": component,
            "displayId": display_id,
            "output": combined[-2000:],
        }

    async def supported_video_codecs(self, serial: str) -> list[str]:
        result = await self.shell(serial, "dumpsys", "media.codec", check=False, timeout=30.0)
        text = (result.stdout + "\n" + result.stderr).lower()
        codecs = ["h264"]
        if "hevc" in text or "video/hevc" in text:
            codecs.append("h265")
        if "av01" in text or "video/av01" in text or "video/av1" in text:
            codecs.append("av1")
        return codecs

    async def display_state(self, serial: str) -> str:
        result = await self.shell(serial, "dumpsys", "display", check=False, timeout=30.0)
        return result.stdout

    async def get_state(self, serial: str) -> str:
        result = await self.run("-s", serial, "get-state", check=False)
        if result.returncode != 0:
            return "disconnected"
        return result.stdout.strip() or "unknown"

    async def push(self, serial: str, local: Path, remote: str) -> None:
        await self.run("-s", serial, "push", str(local), remote, timeout=120.0)

    async def mkdir(self, serial: str, remote_directory: str) -> None:
        await self.run("-s", serial, "shell", "mkdir", "-p", remote_directory, timeout=30.0)

    async def media_scan(self, serial: str, remote_path: str) -> None:
        await self.run(
            "-s", serial, "shell", "am", "broadcast",
            "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
            "-d", f"file://{remote_path}", check=False, timeout=30.0,
        )

    async def remove_file(self, serial: str, remote_path: str) -> None:
        # Arguments are passed directly to adb; no shell command string is built.
        result = await self.run("-s", serial, "shell", "rm", "-f", remote_path, check=False, timeout=30.0)
        if result.returncode != 0:
            raise AdbCommandError(
                "unable to delete Android file",
                details={"serial": serial, "path": remote_path, "stderr": result.stderr.strip()},
            )

    async def create_forward(self, serial: str, local_port: int, socket_name: str) -> None:
        await self.run(
            "-s",
            serial,
            "forward",
            f"tcp:{local_port}",
            f"localabstract:{socket_name}",
        )

    async def remove_forward(self, serial: str, local_port: int) -> None:
        await self.run(
            "-s",
            serial,
            "forward",
            "--remove",
            f"tcp:{local_port}",
            check=False,
        )

    async def spawn_server(self, serial: str, server_args: Sequence[str]) -> SpawnedAdbProcess:
        executable = self.resolved_executable()
        argv = (
            executable,
            "-s",
            serial,
            "shell",
            "CLASSPATH=/data/local/tmp/scrcpy-server.jar",
            "app_process",
            "/",
            "com.genymobile.scrcpy.Server",
            *server_args,
        )
        try:
            return await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env(),
                **_subprocess_creation_kwargs(),
            )
        except OSError as exc:
            raise AdbUnavailableError(
                f"Unable to launch scrcpy server through ADB: {exc}",
                details={"argv": list(argv)},
            ) from exc
