from __future__ import annotations

import shlex

import pytest

from droid_web_display.adb.client import AdbClient, AdbCommandResult, _remote_shell_command


def test_remote_shell_command_round_trips_literal_arguments() -> None:
    args = (
        "rm",
        "-f",
        "/sdcard/Download/name with spaces;$(touch /data/local/tmp/pwned)`id`'quote.txt",
    )
    command = _remote_shell_command(args)
    assert shlex.split(command) == list(args)
    assert ";$(touch" in command
    assert command != " ".join(args)


@pytest.mark.parametrize("value", ["bad\nname", "bad\rname", "bad\x00name", "bad\tname", "bad\x7fname"])
def test_remote_shell_command_rejects_control_characters(value: str) -> None:
    with pytest.raises(ValueError, match="control characters"):
        _remote_shell_command(("rm", value))


class CaptureAdb(AdbClient):
    def __init__(self) -> None:
        super().__init__("adb")
        self.captured: tuple[str, ...] | None = None

    async def run(self, *args: str, timeout=None, check=True) -> AdbCommandResult:  # type: ignore[override]
        self.captured = args
        return AdbCommandResult(args, 0, "", "")


@pytest.mark.asyncio
async def test_shell_sends_one_safely_quoted_remote_command() -> None:
    client = CaptureAdb()
    path = "/sdcard/Download/report; echo injected"
    await client.shell("PHONE", "mkdir", "-p", path)

    assert client.captured is not None
    assert client.captured[:3] == ("-s", "PHONE", "shell")
    assert len(client.captured) == 4
    assert shlex.split(client.captured[3]) == ["mkdir", "-p", path]
