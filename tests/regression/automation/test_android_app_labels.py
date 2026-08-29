from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from droid_web_display.adb.app_labels import parse_scrcpy_app_list
from droid_web_display.adb.client import AdbClient, AdbCommandResult
from droid_web_display.scrcpy.artifact import ScrcpyArtifact

SCRCPY_APP_LIST = (
    "[server] INFO: Device: [samsung] Samsung SM-G980F (Android 13)\n"
    "[server] INFO: Processing Android apps... (this may take some time)\n"
    "[server] INFO: List of apps:\n"
    " * Samsung Internet              com.sec.android.app.sbrowser\n"
    " - YouTube Music                 com.google.android.apps.youtube.music\n"
    " - Преводач                      com.example.translator\n"
    " - Android application name longer than thirty characters\n"
    "                                  com.example.longlabel"
)

DUMPSYS = """
Display #0 (activities from top to bottom):
  * Task{aaa #42 type=standard A=10123:com.sec.android.app.sbrowser U=0 visible=true}
    topResumedActivity=ActivityRecord{bbb u0 com.sec.android.app.sbrowser/.SBrowserMainActivity t42}
  * Task{ccc #43 type=standard A=10124:com.google.android.apps.youtube.music U=0 visible=false}
    * Hist #0: ActivityRecord{ddd u0 com.google.android.apps.youtube.music/.MainActivity t43}
"""


class _CompletedProcess:
    def __init__(self, stdout: str, stderr: str = "", returncode: int = 0) -> None:
        self.returncode: int | None = returncode
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_data(stdout.encode("utf-8"))
        self.stdout.feed_eof()
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_data(stderr.encode("utf-8"))
        self.stderr.feed_eof()

    async def wait(self) -> int:
        return int(self.returncode or 0)

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = -9


class _AndroidLabelAdb(AdbClient):
    def __init__(self, artifact: ScrcpyArtifact) -> None:
        super().__init__("adb", scrcpy_artifact_loader=lambda: artifact)
        self.pushes: list[tuple[str, Path, str]] = []
        self.server_arguments: list[tuple[str, tuple[str, ...]]] = []

    async def push(self, serial: str, local: Path, remote: str) -> None:
        self.pushes.append((serial, local, remote))

    async def spawn_server(self, serial: str, server_args: Sequence[str]) -> _CompletedProcess:
        self.server_arguments.append((serial, tuple(server_args)))
        return _CompletedProcess(SCRCPY_APP_LIST)

    async def shell(
        self,
        serial: str,
        *args: str,
        check: bool = True,
        timeout: float | None = None,
    ) -> AdbCommandResult:
        assert serial == "PHONE"
        assert args == ("dumpsys", "activity", "activities")
        return AdbCommandResult(args, 0, DUMPSYS, "")


class _PackageFallbackAdb(AdbClient):
    async def shell(
        self,
        serial: str,
        *args: str,
        check: bool = True,
        timeout: float | None = None,
    ) -> AdbCommandResult:
        assert serial == "PHONE"
        assert args[:3] == ("cmd", "package", "query-activities")
        return AdbCommandResult(
            args,
            0,
            "com.sec.android.app.sbrowser/.SBrowserMainActivity\n",
            "",
        )


def test_scrcpy_app_list_parser_preserves_android_application_names() -> None:
    labels = parse_scrcpy_app_list(SCRCPY_APP_LIST)

    assert labels["com.sec.android.app.sbrowser"] == "Samsung Internet"
    assert labels["com.google.android.apps.youtube.music"] == "YouTube Music"
    assert labels["com.example.translator"] == "Преводач"
    assert labels["com.example.longlabel"] == "Android application name longer than thirty characters"


async def test_package_discovery_remains_available_without_scrcpy_artifact() -> None:
    apps = await _PackageFallbackAdb("adb").list_launchable_apps("PHONE")

    assert apps == [{"label": "Sbrowser", "packageName": "com.sec.android.app.sbrowser"}]


async def test_installed_and_running_dropdowns_share_android_labels(tmp_path: Path) -> None:
    artifact = ScrcpyArtifact(
        tmp_path / "scrcpy-server-v4.1",
        "4.1",
        "a" * 40,
        "b" * 64,
        "scrcpy-4.1",
    )
    adb = _AndroidLabelAdb(artifact)

    installed = await adb.list_launchable_apps("PHONE")
    running = await adb.list_running_gui_apps("PHONE")

    installed_by_package = {item["packageName"]: item["label"] for item in installed}
    running_by_package = {item.package_name: item.label for item in running}
    assert installed_by_package["com.sec.android.app.sbrowser"] == "Samsung Internet"
    assert running_by_package["com.sec.android.app.sbrowser"] == "Samsung Internet"
    assert installed_by_package["com.google.android.apps.youtube.music"] == "YouTube Music"
    assert running_by_package["com.google.android.apps.youtube.music"] == "YouTube Music"
    assert len(adb.server_arguments) == 1
    assert "list_apps=true" in adb.server_arguments[0][1]
    assert "cleanup=false" in adb.server_arguments[0][1]
    assert adb.pushes == [("PHONE", artifact.path, "/data/local/tmp/scrcpy-server.jar")]
