import asyncio

from droid_web_display.adb import client as adb_client


class _FakeProcess:
    returncode = 0

    async def communicate(self) -> tuple[bytes, bytes]:
        return b"ok\n", b""

    async def wait(self) -> int:
        return 0

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass


def test_windows_creation_kwargs_hide_console() -> None:
    assert adb_client._subprocess_creation_kwargs("nt") == {"creationflags": 0x08000000}
    assert adb_client._subprocess_creation_kwargs("posix") == {}


def test_adb_run_applies_background_creation_flags(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_spawn(*args: str, **kwargs: object) -> _FakeProcess:
        captured.update(kwargs)
        return _FakeProcess()

    client = adb_client.AdbClient("adb")
    monkeypatch.setattr(client, "resolved_executable", lambda: "adb.exe")
    monkeypatch.setattr(adb_client, "_subprocess_creation_kwargs", lambda: {"creationflags": 0x08000000})
    monkeypatch.setattr(adb_client.asyncio, "create_subprocess_exec", fake_spawn)

    result = asyncio.run(client.run("version"))

    assert result.returncode == 0
    assert captured["creationflags"] == 0x08000000


def test_scrcpy_server_spawn_applies_background_creation_flags(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_spawn(*args: str, **kwargs: object) -> _FakeProcess:
        captured.update(kwargs)
        return _FakeProcess()

    client = adb_client.AdbClient("adb")
    monkeypatch.setattr(client, "resolved_executable", lambda: "adb.exe")
    monkeypatch.setattr(adb_client, "_subprocess_creation_kwargs", lambda: {"creationflags": 0x08000000})
    monkeypatch.setattr(adb_client.asyncio, "create_subprocess_exec", fake_spawn)

    process = asyncio.run(client.spawn_server("SERIAL", ["1.0"]))

    assert process.returncode == 0
    assert captured["creationflags"] == 0x08000000
