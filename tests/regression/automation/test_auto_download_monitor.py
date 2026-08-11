from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from gpt_bridge.transfers.adb_sync import AdbSyncEntry, AdbSyncStat
from gpt_bridge.transfers.manager import TransferManager
from gpt_bridge.transfers.models import TransferState
from gpt_bridge.transfers.monitor import AutoDownloadConfig, AutoDownloadMonitor


class FakeAdb:
    def __init__(self, sync: "FakeSync") -> None:
        self.sync = sync
        self.removed: list[str] = []

    async def get_state(self, serial: str) -> str:
        return "device"

    async def mkdir(self, serial: str, remote_directory: str) -> None:
        return None

    async def remove_file(self, serial: str, remote_path: str) -> None:
        self.removed.append(remote_path)
        self.sync.remote.pop(remote_path, None)
        self.sync.modified.pop(remote_path, None)


class FakeSync:
    def __init__(self) -> None:
        self.remote: dict[str, bytes] = {}
        self.modified: dict[str, int] = {}

    def put(self, path: str, data: bytes, modified: int) -> None:
        self.remote[path] = data
        self.modified[path] = modified

    async def list(self, serial: str, path: str):
        prefix = path.rstrip("/") + "/"
        result = []
        for remote_path, data in self.remote.items():
            if not remote_path.startswith(prefix):
                continue
            name = remote_path[len(prefix):]
            if "/" in name:
                continue
            result.append(AdbSyncEntry(name, 0o100664, len(data), self.modified[remote_path]))
        return result

    async def stat(self, serial: str, path: str) -> AdbSyncStat:
        data = self.remote.get(path)
        return AdbSyncStat(0 if data is None else 0o100664, 0 if data is None else len(data), self.modified.get(path, 0))

    async def pull(self, serial: str, remote_path: str, local_path: Path, *, progress=None):
        data = self.remote[remote_path]
        local_path.write_bytes(data)
        if progress:
            await progress(len(data), len(data))
        return len(data)

    async def push(self, serial: str, local_path: Path, remote_path: str, *, progress=None):
        data = local_path.read_bytes()
        self.remote[remote_path] = data
        self.modified[remote_path] = max(self.modified.values(), default=0) + 1
        if progress:
            await progress(len(data), len(data))
        return len(data)


async def wait_completed(manager: TransferManager) -> None:
    for _ in range(200):
        if manager.list_records() and manager.list_records()[0].state in {TransferState.COMPLETED, TransferState.FAILED}:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("automatic transfer did not finish")


@pytest.mark.asyncio
async def test_new_stable_file_downloads_once_and_persists(tmp_path: Path, monkeypatch) -> None:
    clock = [100.0]
    monkeypatch.setattr("gpt_bridge.transfers.monitor.time.time", lambda: clock[0])
    sync = FakeSync()
    sync.put("/sdcard/Download/existing.txt", b"existing", 1)
    adb = FakeAdb(sync)
    manager = TransferManager(adb, sync, data_directory=tmp_path / "data", destination_profiles={"default-downloads": tmp_path / "downloads"})  # type: ignore[arg-type]
    await manager.start()
    monitor = AutoDownloadMonitor(adb, manager, data_directory=tmp_path / "data")  # type: ignore[arg-type]
    await monitor.configure(AutoDownloadConfig(serial="PHONE", stability_seconds=1, stability_observations=2))

    await monitor.scan_now()  # Existing file becomes baseline.
    assert not manager.list_records()

    sync.put("/sdcard/Download/new.txt", b"new-content", 2)
    clock[0] = 101.0
    await monitor.scan_now()
    assert not manager.list_records()
    clock[0] = 103.0
    await monitor.scan_now()
    await wait_completed(manager)
    clock[0] = 104.0
    await monitor.scan_now()  # Reconcile completed transfer.

    records = manager.list_records()
    assert len(records) == 1
    assert records[0].state == TransferState.COMPLETED
    assert (tmp_path / "downloads" / "new.txt").read_bytes() == b"new-content"
    assert monitor.snapshot()["runtime"]["downloadsCompleted"] == 1

    clock[0] = 110.0
    await monitor.scan_now()
    assert len(manager.list_records()) == 1  # unchanged file is not pulled twice

    await monitor.close()
    reloaded = AutoDownloadMonitor(adb, manager, data_directory=tmp_path / "data")  # type: ignore[arg-type]
    await reloaded.start()
    try:
        assert reloaded.snapshot()["processedFingerprints"] >= 2
        await reloaded.configure(AutoDownloadConfig(serial="PHONE", stability_seconds=1, stability_observations=2))
        await reloaded.scan_now()
        assert len(manager.list_records()) == 1
    finally:
        await reloaded.close()
        await manager.close()


@pytest.mark.asyncio
async def test_changing_and_partial_files_are_not_pulled_prematurely(tmp_path: Path, monkeypatch) -> None:
    clock = [10.0]
    monkeypatch.setattr("gpt_bridge.transfers.monitor.time.time", lambda: clock[0])
    sync = FakeSync()
    adb = FakeAdb(sync)
    manager = TransferManager(adb, sync, data_directory=tmp_path / "data", destination_profiles={"default-downloads": tmp_path / "downloads"})  # type: ignore[arg-type]
    await manager.start()
    monitor = AutoDownloadMonitor(adb, manager, data_directory=tmp_path / "data")  # type: ignore[arg-type]
    await monitor.configure(AutoDownloadConfig(serial="PHONE", include_existing=True, stability_seconds=2, stability_observations=2))

    sync.put("/sdcard/Download/file.bin", b"a", 1)
    sync.put("/sdcard/Download/browser.crdownload", b"partial", 1)
    await monitor.scan_now()
    clock[0] = 11.0
    sync.put("/sdcard/Download/file.bin", b"ab", 2)
    await monitor.scan_now()
    assert not manager.list_records()
    clock[0] = 14.0
    await monitor.scan_now()
    await wait_completed(manager)
    assert [item.filename for item in manager.list_records()] == ["file.bin"]
    await monitor.close()
    await manager.close()


@pytest.mark.asyncio
async def test_delete_after_verified_success_only(tmp_path: Path, monkeypatch) -> None:
    clock = [50.0]
    monkeypatch.setattr("gpt_bridge.transfers.monitor.time.time", lambda: clock[0])
    sync = FakeSync()
    sync.put("/sdcard/Download/delete-me.txt", b"verified", 5)
    adb = FakeAdb(sync)
    manager = TransferManager(adb, sync, data_directory=tmp_path / "data", destination_profiles={"default-downloads": tmp_path / "downloads"})  # type: ignore[arg-type]
    await manager.start()
    monitor = AutoDownloadMonitor(adb, manager, data_directory=tmp_path / "data")  # type: ignore[arg-type]
    await monitor.configure(AutoDownloadConfig(
        serial="PHONE", include_existing=True, delete_after_verified=True,
        stability_seconds=1, stability_observations=2,
    ))
    await monitor.scan_now()
    clock[0] = 52.0
    await monitor.scan_now()
    await wait_completed(manager)
    clock[0] = 53.0
    await monitor.scan_now()
    assert adb.removed == ["/sdcard/Download/delete-me.txt"]
    assert "/sdcard/Download/delete-me.txt" not in sync.remote
    assert monitor.snapshot()["runtime"]["deletionsCompleted"] == 1
    await monitor.close()
    await manager.close()


@pytest.mark.asyncio
async def test_pc_to_android_uploads_stable_files_and_prevents_bounce(tmp_path: Path, monkeypatch) -> None:
    clock = [200.0]
    monkeypatch.setattr("gpt_bridge.transfers.monitor.time.time", lambda: clock[0])
    sync = FakeSync()
    adb = FakeAdb(sync)
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "existing.txt").write_text("baseline", encoding="utf-8")
    manager = TransferManager(
        adb,
        sync,
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": downloads},
    )  # type: ignore[arg-type]
    await manager.start()
    monitor = AutoDownloadMonitor(adb, manager, data_directory=tmp_path / "data")  # type: ignore[arg-type]
    await monitor.configure(AutoDownloadConfig(
        enabled=True,
        pc_to_android_enabled=True,
        serial="PHONE",
        stability_seconds=1,
        stability_observations=2,
    ))

    await monitor.scan_now()  # Baseline both empty Android and existing PC file.
    assert not manager.list_records()

    local = downloads / "from-pc.txt"
    local.write_bytes(b"pc-to-android")
    clock[0] = 201.0
    await monitor.scan_now()
    assert not manager.list_records()
    clock[0] = 203.0
    await monitor.scan_now()
    await wait_completed(manager)
    clock[0] = 204.0
    await monitor.scan_now()  # Reconcile upload before scanning Android.

    assert sync.remote["/sdcard/Download/from-pc.txt"] == b"pc-to-android"
    records = manager.list_records()
    assert len(records) == 1
    assert records[0].state == TransferState.COMPLETED
    assert records[0].direction.value == "upload"
    snapshot = monitor.snapshot()
    assert snapshot["runtime"]["uploadsCompleted"] == 1
    assert snapshot["runtime"]["downloadsQueued"] == 0
    assert snapshot["processedPcFingerprints"] >= 2

    clock[0] = 210.0
    await monitor.scan_now()
    assert len(manager.list_records()) == 1  # Uploaded Android file is not downloaded back.

    await monitor.close()
    await manager.close()
