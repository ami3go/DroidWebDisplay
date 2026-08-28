from __future__ import annotations

import shlex

import pytest

from droid_web_display.adb.client import AdbClient, AdbCommandResult


@pytest.mark.asyncio
async def test_remove_path_quotes_the_complete_remote_android_command(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AdbClient("adb")
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    async def fake_run(*args: str, **kwargs: object) -> AdbCommandResult:
        calls.append((args, kwargs))
        return AdbCommandResult(("adb", *args), 0, "", "")

    monkeypatch.setattr(client, "run", fake_run)
    path = "/sdcard/Download/report $(touch injected); it's final.txt"

    await client.remove_path("PHONE", path)
    await client.remove_path("PHONE", "/sdcard/Download/old folder", recursive=True)

    assert calls == [
        (
            ("-s", "PHONE", "shell", shlex.join(("rm", "-f", "--", path))),
            {"check": False, "timeout": 30.0},
        ),
        (
            ("-s", "PHONE", "shell", shlex.join(("rm", "-rf", "--", "/sdcard/Download/old folder"))),
            {"check": False, "timeout": 30.0},
        ),
    ]


@pytest.mark.asyncio
async def test_media_scan_quotes_deleted_picture_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AdbClient("adb")
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    async def fake_run(*args: str, **kwargs: object) -> AdbCommandResult:
        calls.append((args, kwargs))
        return AdbCommandResult(("adb", *args), 0, "", "")

    monkeypatch.setattr(client, "run", fake_run)
    path = "/sdcard/DCIM/Camera/holiday; selected photo.jpg"

    await client.media_scan("PHONE", path)

    expected = shlex.join(
        (
            "am",
            "broadcast",
            "-a",
            "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
            "-d",
            f"file://{path}",
        )
    )
    assert calls == [
        (("-s", "PHONE", "shell", expected), {"check": False, "timeout": 30.0}),
    ]
