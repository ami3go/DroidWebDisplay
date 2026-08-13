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


@pytest.mark.asyncio
async def test_server_exit_during_startup_cleans_only_new_session(tmp_path: Path) -> None:
    class ExitOnSpawnAdb(FakeAdb):
        async def spawn_server(self, serial, server_args):
            process = await super().spawn_server(serial, server_args)
            process.exit(23)
            return process

    adb = ExitOnSpawnAdb([AndroidDevice("PHONE", "device")])
    manager = SessionManager(
        adb,
        artifact(tmp_path),
        connect_timeout=0.2,
        connect_retry_interval=0.01,
        monitor_interval=10,
    )

    with pytest.raises(Exception):
        await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))

    assert "PHONE" not in manager._device_sessions
    assert not adb.forward_servers
    failed = manager.list_sessions()[-1]
    assert failed.state == SessionState.FAILED
    assert failed.stop_reason == "start_failed"
    await manager.close()


@pytest.mark.asyncio
async def test_default_capacity_rejects_fifth_session_atomically(tmp_path: Path) -> None:
    from droid_web_display.errors import SessionConflictError

    adb = FakeAdb([AndroidDevice("PHONE", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=10)
    sessions = [
        await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
        for _ in range(4)
    ]
    assert manager.session_capacity("PHONE") == {
        "serial": "PHONE",
        "activeSessions": 4,
        "maximumSessions": 4,
        "availableSlots": 0,
    }
    with pytest.raises(SessionConflictError) as exc_info:
        await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
    assert exc_info.value.details["maximumSessions"] == 4
    assert len(manager.list_sessions_for_device("PHONE")) == 4
    assert len(adb.forward_servers) == 4
    await manager.close()


@pytest.mark.asyncio
async def test_stopping_session_releases_capacity_for_replacement(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=10, maximum_sessions_per_device=2)
    first = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
    second = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
    assert manager.session_capacity("PHONE")["availableSlots"] == 0

    await manager.stop_session(first.session_id)
    assert manager.session_capacity("PHONE")["availableSlots"] == 1
    replacement = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))

    assert replacement.state == SessionState.RUNNING
    assert {item.session_id for item in manager.list_sessions_for_device("PHONE")} == {second.session_id, replacement.session_id}
    await manager.close()


@pytest.mark.asyncio
async def test_failed_session_releases_slot_without_affecting_sibling(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=10, maximum_sessions_per_device=2)
    first = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
    second = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
    adb.processes[0].exit(9)
    await wait_for_state(first, SessionState.DISCONNECTED)

    assert second.state == SessionState.RUNNING
    assert manager.session_capacity("PHONE")["availableSlots"] == 1
    replacement = await manager.start_session(serial="PHONE", options=SessionOptions(audio=False))
    assert replacement.state == SessionState.RUNNING
    assert second.local_port in adb.forward_servers
    await manager.close()


@pytest.mark.asyncio
async def test_capacity_is_independent_per_android_device(tmp_path: Path) -> None:
    from droid_web_display.errors import SessionConflictError

    adb = FakeAdb([AndroidDevice("A", "device"), AndroidDevice("B", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=10, maximum_sessions_per_device=1)
    a = await manager.start_session(serial="A", options=SessionOptions(audio=False))
    b = await manager.start_session(serial="B", options=SessionOptions(audio=False))
    assert a.state == b.state == SessionState.RUNNING
    with pytest.raises(SessionConflictError):
        await manager.start_session(serial="A", options=SessionOptions(audio=False))
    assert manager.session_capacity("A")["availableSlots"] == 0
    assert manager.session_capacity("B")["availableSlots"] == 0
    await manager.close()
