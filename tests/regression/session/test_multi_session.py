import asyncio
from pathlib import Path

import pytest

from droid_web_display.models import AndroidDevice, SessionOptions, SessionState
from droid_web_display.scrcpy.artifact import ScrcpyArtifact
from droid_web_display.scrcpy.session import SessionManager
from tests.regression.session.fakes import FakeAdb


def artifact(tmp_path: Path) -> ScrcpyArtifact:
    path = tmp_path / "scrcpy-server-v4.1"
    path.write_bytes(b"verified-test-server")
    return ScrcpyArtifact(path, "4.1", "a" * 40, "b" * 64, "scrcpy-4.1")


async def wait_for_state(session, state: SessionState) -> None:
    for _ in range(200):
        if session.state == state:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"session {session.session_id} did not reach {state.value}; got {session.state.value}")


@pytest.mark.asyncio
async def test_two_sessions_can_run_on_same_serial(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device", model="Test")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=10)

    first = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
    second = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))

    assert first.state == SessionState.RUNNING
    assert second.state == SessionState.RUNNING
    assert first.session_id != second.session_id
    assert {item.session_id for item in manager.list_sessions_for_device("PHONE")} == {first.session_id, second.session_id}
    await manager.close()


@pytest.mark.asyncio
async def test_four_sessions_same_serial_have_unique_transport_resources(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=10)

    sessions = [
        await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
        for _ in range(4)
    ]

    assert len({item.session_id for item in sessions}) == 4
    assert len({item.scid for item in sessions}) == 4
    assert len({item.socket_name for item in sessions}) == 4
    assert len({item.local_port for item in sessions}) == 4
    assert set(adb.forward_servers) == {item.local_port for item in sessions}
    assert len(manager.list_sessions_for_device("PHONE")) == 4
    await manager.close()


@pytest.mark.asyncio
async def test_sessions_on_different_devices_are_indexed_independently(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("A", "device"), AndroidDevice("B", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=10)

    a = await manager.start_session(serial="A", options=SessionOptions(audio=False))
    b = await manager.start_session(serial="B", options=SessionOptions(audio=False))

    assert [item.session_id for item in manager.list_sessions_for_device("A")] == [a.session_id]
    assert [item.session_id for item in manager.list_sessions_for_device("B")] == [b.session_id]
    await manager.close()


@pytest.mark.asyncio
async def test_stopping_one_session_does_not_touch_siblings(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=10)
    first = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
    second = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))

    await manager.stop_session(first.session_id)

    assert first.state == SessionState.STOPPED
    assert second.state == SessionState.RUNNING
    assert first.local_port not in adb.forward_servers
    assert second.local_port in adb.forward_servers
    assert [item.session_id for item in manager.list_sessions_for_device("PHONE")] == [second.session_id]
    await manager.close()


@pytest.mark.asyncio
async def test_server_failure_is_isolated_to_one_session(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=10)
    first = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
    second = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))

    adb.processes[0].exit(17)
    await wait_for_state(first, SessionState.DISCONNECTED)

    assert second.state == SessionState.RUNNING
    assert second.local_port in adb.forward_servers
    assert [item.session_id for item in manager.list_sessions_for_device("PHONE")] == [second.session_id]
    await manager.close()


@pytest.mark.asyncio
async def test_device_disconnect_stops_all_sessions_for_that_serial_only(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device"), AndroidDevice("OTHER", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=0.02)
    phone_sessions = [
        await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
        for _ in range(3)
    ]
    other = await manager.start_session(serial="OTHER", options=SessionOptions(audio=False))

    adb.devices = [AndroidDevice("OTHER", "device")]
    await asyncio.gather(*(wait_for_state(item, SessionState.DISCONNECTED) for item in phone_sessions))

    assert other.state == SessionState.RUNNING
    assert "PHONE" not in manager._device_sessions
    assert [item.session_id for item in manager.list_sessions_for_device("OTHER")] == [other.session_id]
    await manager.close()
