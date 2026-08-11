from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from droid_web_display.transfers.adb_sync import AdbSyncEntry, AdbSyncStat
from droid_web_display.transfers.manager import TransferManager
from droid_web_display.transfers.models import DuplicatePolicy, TransferState


class FakeAdb:
    async def get_state(self, serial: str) -> str:
        return "device"

    async def mkdir(self, serial: str, remote_directory: str) -> None:
        return None


class FakeSync:
    def __init__(self) -> None:
        self.remote: dict[str, bytes] = {"/sdcard/Download/remote.txt": b"remote-content"}
        self.fail_push_once = False
        self.block_push = False
        self.started = asyncio.Event()

    async def list(self, serial: str, path: str):
        return [AdbSyncEntry("remote.txt", 0o100664, len(self.remote["/sdcard/Download/remote.txt"]), 1)]

    async def stat(self, serial: str, path: str) -> AdbSyncStat:
        data = self.remote.get(path)
        return AdbSyncStat(0 if data is None else 0o100664, 0 if data is None else len(data), 1)

    async def push(self, serial: str, local_path: Path, remote_path: str, *, progress=None, mode=0o100664):
        self.started.set()
        if self.block_push:
            await asyncio.sleep(60)
        if self.fail_push_once:
            self.fail_push_once = False
            raise RuntimeError("simulated transfer failure")
        data = local_path.read_bytes()
        if progress:
            await progress(len(data), len(data))
        self.remote[remote_path] = data
        return len(data)

    async def pull(self, serial: str, remote_path: str, local_path: Path, *, progress=None):
        data = self.remote[remote_path]
        local_path.write_bytes(data)
        if progress:
            await progress(len(data), len(data))
        return len(data)


async def wait_final(manager: TransferManager, transfer_id: str):
    for _ in range(200):
        record = manager.get(transfer_id)
        if record.state in {TransferState.COMPLETED, TransferState.FAILED, TransferState.CANCELLED}:
            return record
        await asyncio.sleep(0.01)
    raise AssertionError("transfer did not finish")


@pytest.mark.asyncio
async def test_upload_download_verification_and_listing(tmp_path: Path) -> None:
    sync = FakeSync()
    manager = TransferManager(FakeAdb(), sync, data_directory=tmp_path / "data", destination_profiles={"default-downloads": tmp_path / "downloads"})  # type: ignore[arg-type]
    await manager.start()
    try:
        entries = await manager.list_android("PHONE", "/sdcard/Download")
        assert entries[0].name == "remote.txt"

        spool = tmp_path / "spool.bin"
        spool.write_bytes(b"upload-content")
        upload = await manager.enqueue_upload(serial="PHONE", spool_path=spool, original_filename="upload.bin", size=14, destination_directory="/sdcard/Download")
        upload = await wait_final(manager, upload.transfer_id)
        assert upload.state == TransferState.COMPLETED
        assert upload.verification == "size-match"
        assert sync.remote["/sdcard/Download/upload.bin"] == b"upload-content"

        download = await manager.enqueue_download(serial="PHONE", source_path="/sdcard/Download/remote.txt")
        download = await wait_final(manager, download.transfer_id)
        assert download.state == TransferState.COMPLETED
        assert Path(download.destination_path).read_bytes() == b"remote-content"
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_cancel_and_retry(tmp_path: Path) -> None:
    sync = FakeSync()
    manager = TransferManager(FakeAdb(), sync, data_directory=tmp_path / "data", destination_profiles={"default-downloads": tmp_path / "downloads"})  # type: ignore[arg-type]
    await manager.start()
    try:
        spool = tmp_path / "cancel.bin"
        spool.write_bytes(b"cancel-me")
        sync.block_push = True
        transfer = await manager.enqueue_upload(serial="PHONE", spool_path=spool, original_filename="cancel.bin", size=9, destination_directory="/sdcard/Download")
        await sync.started.wait()
        cancelled = await manager.cancel(transfer.transfer_id)
        assert cancelled.state == TransferState.CANCELLED

        sync.block_push = False
        retried = await manager.retry(transfer.transfer_id)
        completed = await wait_final(manager, retried.transfer_id)
        assert completed.state == TransferState.COMPLETED
        assert completed.retry_count == 1
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_failed_upload_is_retryable_and_duplicate_is_renamed(tmp_path: Path) -> None:
    sync = FakeSync()
    sync.remote["/sdcard/Download/upload.bin"] = b"existing"
    sync.fail_push_once = True
    manager = TransferManager(FakeAdb(), sync, data_directory=tmp_path / "data", destination_profiles={"default-downloads": tmp_path / "downloads"})  # type: ignore[arg-type]
    await manager.start()
    try:
        spool = tmp_path / "upload.bin"
        spool.write_bytes(b"new")
        transfer = await manager.enqueue_upload(serial="PHONE", spool_path=spool, original_filename="upload.bin", size=3, destination_directory="/sdcard/Download", duplicate_policy=DuplicatePolicy.RENAME)
        failed = await wait_final(manager, transfer.transfer_id)
        assert failed.state == TransferState.FAILED
        await manager.retry(failed.transfer_id)
        completed = await wait_final(manager, failed.transfer_id)
        assert completed.state == TransferState.COMPLETED
        assert completed.destination_path == "/sdcard/Download/upload (1).bin"
    finally:
        await manager.close()
