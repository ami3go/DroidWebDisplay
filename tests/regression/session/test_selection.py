from pathlib import Path

import pytest

from gpt_bridge.errors import DeviceNotReadyError, MultipleDevicesError
from gpt_bridge.models import AndroidDevice
from gpt_bridge.scrcpy.artifact import ScrcpyArtifact
from gpt_bridge.scrcpy.session import SessionManager
from tests.regression.session.fakes import FakeAdb


def artifact(tmp_path: Path) -> ScrcpyArtifact:
    path = tmp_path / "server"
    path.write_bytes(b"server")
    return ScrcpyArtifact(path, "4.1", "a" * 40, "b" * 64, "scrcpy-4.1")


@pytest.mark.asyncio
async def test_single_ready_device_selected_implicitly(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("A", "device"), AndroidDevice("B", "unauthorized")])
    manager = SessionManager(adb, artifact(tmp_path))
    selected = await manager.select_device(None)
    assert selected.serial == "A"


@pytest.mark.asyncio
async def test_multiple_ready_devices_require_explicit_serial(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("A", "device"), AndroidDevice("B", "device")])
    manager = SessionManager(adb, artifact(tmp_path))
    with pytest.raises(MultipleDevicesError):
        await manager.select_device(None)
    assert (await manager.select_device("B")).serial == "B"


@pytest.mark.asyncio
async def test_unauthorized_explicit_device_rejected(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("A", "unauthorized")])
    manager = SessionManager(adb, artifact(tmp_path))
    with pytest.raises(DeviceNotReadyError) as caught:
        await manager.select_device("A")
    assert caught.value.details["authorizationRequired"] is True
