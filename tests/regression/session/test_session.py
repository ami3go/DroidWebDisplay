import asyncio
from pathlib import Path

import pytest

from droid_web_display.models import AndroidDevice, ChannelName, SessionOptions, SessionState
from droid_web_display.scrcpy.artifact import ScrcpyArtifact
from droid_web_display.scrcpy.session import SessionManager
from tests.regression.session.fakes import FakeAdb


def artifact(tmp_path: Path) -> ScrcpyArtifact:
    path = tmp_path / "scrcpy-server-v4.1"
    path.write_bytes(b"verified-test-server")
    return ScrcpyArtifact(path, "4.1", "a" * 40, "b" * 64, "scrcpy-4.1")


@pytest.mark.asyncio
async def test_session_opens_video_then_control_and_preserves_bytes(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device", model="Test")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0)
    session = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
    assert session.state == SessionState.RUNNING
    assert tuple(session.channels) == (ChannelName.VIDEO, ChannelName.CONTROL)
    assert adb.pushed[0][2] == "/data/local/tmp/scrcpy-server.jar"
    assert adb.forwards[0][2].startswith("scrcpy_")
    assert "tunnel_forward=true" in adb.server_args[0][1]

    first = await asyncio.wait_for(session.channels[ChannelName.VIDEO].reader.readexactly(65), timeout=1)
    assert first == b"\x00" + b"D" * 64
    assert await asyncio.wait_for(
        session.channels[ChannelName.VIDEO].reader.readexactly(len(b"VIDEO-PAYLOAD")), timeout=1
    ) == b"VIDEO-PAYLOAD"
    assert await asyncio.wait_for(
        session.channels[ChannelName.CONTROL].reader.readexactly(len(b"CONTROL-PAYLOAD")), timeout=1
    ) == b"CONTROL-PAYLOAD"

    stopped = await manager.stop_session(session.session_id)
    assert stopped.state == SessionState.STOPPED
    assert adb.removed == [("PHONE", session.local_port)]
    assert adb.processes[0].terminated is True
    await manager.close()


@pytest.mark.asyncio
async def test_monitor_marks_session_disconnected_without_switching_device(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=0.02)
    session = await manager.start_session(serial="PHONE")
    adb.devices = [AndroidDevice("OTHER", "device")]

    for _ in range(100):
        if session.state == SessionState.DISCONNECTED:
            break
        await asyncio.sleep(0.02)

    assert session.state == SessionState.DISCONNECTED
    assert session.stop_reason == "device_disconnected"
    assert "PHONE" not in manager._device_sessions
    await manager.close()


@pytest.mark.asyncio
async def test_server_termination_marks_session_disconnected(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=10)
    session = await manager.start_session(serial="PHONE")
    adb.processes[0].exit(17)

    for _ in range(100):
        if session.state == SessionState.DISCONNECTED:
            break
        await asyncio.sleep(0.01)

    assert session.state == SessionState.DISCONNECTED
    assert session.stop_reason == "server_terminated"
    assert "17" in (session.error or "")
    await manager.close()

@pytest.mark.asyncio
async def test_first_channel_retries_dead_adb_forward_and_preserves_dummy(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device", model="Test")])
    adb.connection_payloads = [
        b"",
        b"\x00" + b"D" * 64 + b"VIDEO-PAYLOAD",
        b"CONTROL-PAYLOAD",
    ]
    manager = SessionManager(
        adb,
        artifact(tmp_path),
        connect_timeout=2.0,
        connect_retry_interval=0.01,
    )

    session = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))

    assert session.state == SessionState.RUNNING
    assert session.first_channel_attempts >= 2
    assert session.dummy_byte_validated is True
    first = await asyncio.wait_for(
        session.channels[ChannelName.VIDEO].reader.readexactly(65), timeout=1
    )
    assert first == b"\x00" + b"D" * 64
    assert await asyncio.wait_for(
        session.channels[ChannelName.VIDEO].reader.readexactly(len(b"VIDEO-PAYLOAD")), timeout=1
    ) == b"VIDEO-PAYLOAD"

    await manager.stop_session(session.session_id)
    await manager.close()
