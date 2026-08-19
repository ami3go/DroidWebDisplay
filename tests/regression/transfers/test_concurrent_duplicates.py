from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from droid_web_display.transfers.adb_sync import AdbSyncStat
from droid_web_display.transfers.manager import TransferManager
from droid_web_display.transfers.models import DuplicatePolicy, TransferState


class FakeAdb:
    async def get_state(self, _serial: str) -> str:
        return "device"

    async def mkdir(self, _serial: str, _remote_directory: str) -> None:
        return None


class SlowSync:
    def __init__(self) -> None:
        self.remote: dict[str, bytes] = {"/sdcard/Download/source.txt": b"download"}

    async def stat(self, _serial: str, path: str) -> AdbSyncStat:
        data = self.remote.get(path)
        return AdbSyncStat(0 if data is None else 0o100664, 0 if data is None else len(data), 1)

    async def push(self, _serial: str, local_path: Path, remote_path: str, *, progress=None, mode=0o100664) -> int:
        data = local_path.read_bytes()
        await asyncio.sleep(0.03)
        self.remote[remote_path] = data
        if progress:
            await progress(len(data), len(data))
        return len(data)

    async def pull(self, _serial: str, remote_path: str, local_path: Path, *, progress=None) -> int:
        data = self.remote[remote_path]
        await asyncio.sleep(0.03)
        local_path.write_bytes(data)
        if progress:
            await progress(len(data), len(data))
        return len(data)


async def wait_all(manager: TransferManager, transfer_ids: list[str]) -> list:
    for _ in range(300):
        records = [manager.get(item) for item in transfer_ids]
        if all(record.state in {TransferState.COMPLETED, TransferState.FAILED, TransferState.CANCELLED} for record in records):
            return records
        await asyncio.sleep(0.01)
    raise AssertionError("concurrent transfers did not finish")


@pytest.mark.asyncio
async def test_concurrent_upload_rename_reserves_unique_remote_names(tmp_path: Path) -> None:
    sync = SlowSync()
    manager = TransferManager(
        FakeAdb(),  # type: ignore[arg-type]
        sync,  # type: ignore[arg-type]
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
        concurrency=2,
    )
    await manager.start()
    try:
        first_spool = tmp_path / "first.part"
        second_spool = tmp_path / "second.part"
        first_spool.write_bytes(b"first")
        second_spool.write_bytes(b"second")
        first = await manager.enqueue_upload(
            serial="PHONE",
            spool_path=first_spool,
            original_filename="same.txt",
            size=5,
            destination_directory="/sdcard/Download",
            duplicate_policy=DuplicatePolicy.RENAME,
        )
        second = await manager.enqueue_upload(
            serial="PHONE",
            spool_path=second_spool,
            original_filename="same.txt",
            size=6,
            destination_directory="/sdcard/Download",
            duplicate_policy=DuplicatePolicy.RENAME,
        )
        records = await wait_all(manager, [first.transfer_id, second.transfer_id])
        assert all(record.state == TransferState.COMPLETED for record in records)
        assert {record.destination_path for record in records} == {
            "/sdcard/Download/same.txt",
            "/sdcard/Download/same (1).txt",
        }
        assert set(sync.remote[path] for path in {record.destination_path for record in records}) == {b"first", b"second"}
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_concurrent_download_rename_reserves_unique_local_names(tmp_path: Path) -> None:
    sync = SlowSync()
    downloads = tmp_path / "downloads"
    manager = TransferManager(
        FakeAdb(),  # type: ignore[arg-type]
        sync,  # type: ignore[arg-type]
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": downloads},
        concurrency=2,
    )
    await manager.start()
    try:
        first = await manager.enqueue_download(
            serial="PHONE",
            source_path="/sdcard/Download/source.txt",
            duplicate_policy=DuplicatePolicy.RENAME,
        )
        second = await manager.enqueue_download(
            serial="PHONE",
            source_path="/sdcard/Download/source.txt",
            duplicate_policy=DuplicatePolicy.RENAME,
        )
        records = await wait_all(manager, [first.transfer_id, second.transfer_id])
        assert all(record.state == TransferState.COMPLETED for record in records)
        assert {Path(record.destination_path).name for record in records} == {"source.txt", "source (1).txt"}
        assert (downloads / "source.txt").read_bytes() == b"download"
        assert (downloads / "source (1).txt").read_bytes() == b"download"
    finally:
        await manager.close()
