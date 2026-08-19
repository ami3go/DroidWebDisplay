from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from droid_web_display.errors import TransferConflictError
from droid_web_display.transfers.adb_sync import AdbSyncStat
from droid_web_display.transfers.manager import TransferManager
from droid_web_display.transfers.models import TransferState


class FakeAdb:
    async def get_state(self, _serial: str) -> str:
        return "device"


class OversizeSync:
    def __init__(self, size: int) -> None:
        self.size = size
        self.pull_called = False

    async def stat(self, _serial: str, _path: str) -> AdbSyncStat:
        return AdbSyncStat(0o100664, self.size, 1)

    async def pull(self, *_args, **_kwargs):
        self.pull_called = True
        raise AssertionError("oversized download must be rejected before pull")


class OneChunk:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.reads = 0

    async def read(self, _size: int) -> bytes:
        self.reads += 1
        if self.reads == 1:
            return self.data
        return b""


async def wait_final(manager: TransferManager, transfer_id: str):
    for _ in range(100):
        record = manager.get(transfer_id)
        if record.state in {TransferState.COMPLETED, TransferState.FAILED, TransferState.CANCELLED}:
            return record
        await asyncio.sleep(0.01)
    raise AssertionError("transfer did not finish")


@pytest.mark.asyncio
async def test_spooling_reserves_queue_capacity_before_reading_body(tmp_path: Path) -> None:
    manager = TransferManager(
        FakeAdb(),  # type: ignore[arg-type]
        OversizeSync(0),  # type: ignore[arg-type]
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
        maximum_queue_length=1,
        maximum_file_size=1024,
    )
    manager.upload_spool.mkdir(parents=True)
    first = OneChunk(b"first")
    await manager.spool_upload("first.bin", first)

    second = OneChunk(b"second")
    with pytest.raises(TransferConflictError, match="queue is full"):
        await manager.spool_upload("second.bin", second)
    assert second.reads == 0


@pytest.mark.asyncio
async def test_enqueue_failure_removes_unregistered_spool(tmp_path: Path) -> None:
    manager = TransferManager(
        FakeAdb(),  # type: ignore[arg-type]
        OversizeSync(0),  # type: ignore[arg-type]
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
        maximum_queue_length=1,
    )
    manager.upload_spool.mkdir(parents=True)
    manager._reserve_spool("reserved.bin")
    spool = manager.upload_spool / "manual.part"
    spool.write_bytes(b"payload")

    with pytest.raises(TransferConflictError, match="queue is full"):
        await manager.enqueue_upload(
            serial="PHONE",
            spool_path=spool,
            original_filename="manual.bin",
            size=7,
            destination_directory="/sdcard/Download",
        )
    assert not spool.exists()


@pytest.mark.asyncio
async def test_oversized_download_is_rejected_before_data_transfer(tmp_path: Path) -> None:
    sync = OversizeSync(101)
    manager = TransferManager(
        FakeAdb(),  # type: ignore[arg-type]
        sync,  # type: ignore[arg-type]
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
        maximum_file_size=100,
    )
    await manager.start()
    try:
        transfer = await manager.enqueue_download(
            serial="PHONE",
            source_path="/sdcard/Download/too-large.bin",
        )
        record = await wait_final(manager, transfer.transfer_id)
        assert record.state == TransferState.FAILED
        assert "maximum size" in (record.error or "")
        assert sync.pull_called is False
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_startup_removes_unreferenced_spool_files(tmp_path: Path) -> None:
    data = tmp_path / "data"
    spool_dir = data / "upload-spool"
    spool_dir.mkdir(parents=True)
    orphan = spool_dir / "orphan.part"
    orphan.write_bytes(b"stale")
    manager = TransferManager(
        FakeAdb(),  # type: ignore[arg-type]
        OversizeSync(0),  # type: ignore[arg-type]
        data_directory=data,
        destination_profiles={"default-downloads": tmp_path / "downloads"},
    )
    await manager.start()
    try:
        assert not orphan.exists()
    finally:
        await manager.close()
