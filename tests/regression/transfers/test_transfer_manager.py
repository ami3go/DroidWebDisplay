from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from droid_web_display.adb.media_store import AndroidMediaFile
from droid_web_display.errors import TransferNotFoundError, TransferValidationError
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


class DeleteSync:
    def __init__(self) -> None:
        self.entries = {
            "/sdcard/Download/delete-me.txt": (0o100664, 7),
            "/sdcard/Download/folder": (0o040775, 0),
            "/sdcard/Download/folder/child.txt": (0o100664, 5),
        }

    async def stat(self, serial: str, path: str) -> AdbSyncStat:
        mode, size = self.entries.get(path, (0, 0))
        return AdbSyncStat(mode, size, 1)


class DeleteAdb(FakeAdb):
    def __init__(self, sync: DeleteSync) -> None:
        self.sync = sync
        self.removed: list[tuple[str, str, bool]] = []

    async def remove_path(self, serial: str, remote_path: str, *, recursive: bool = False) -> None:
        self.removed.append((serial, remote_path, recursive))
        for path in list(self.sync.entries):
            if path == remote_path or (recursive and path.startswith(f"{remote_path}/")):
                del self.sync.entries[path]


class RecentPicturesAdb(FakeAdb):
    async def list_recent_pictures(self, serial: str, *, limit: int = 50):
        return [
            AndroidMediaFile("/storage/emulated/0/Pictures/older.png", 10, 100),
            AndroidMediaFile("/storage/emulated/0/DCIM/Camera/newer.jpg", 20, 300),
            AndroidMediaFile("/sdcard/Android/media/private-looking.jpg", 30, 400),
            AndroidMediaFile("/storage/emulated/0/DCIM/Camera/newer.jpg", 20, 300),
        ]


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


@pytest.mark.asyncio
async def test_delete_android_file_and_folder_protects_storage_roots(tmp_path: Path) -> None:
    sync = DeleteSync()
    adb = DeleteAdb(sync)
    manager = TransferManager(adb, sync, data_directory=tmp_path / "data", destination_profiles={"default-downloads": tmp_path / "downloads"})  # type: ignore[arg-type]

    deleted_file = await manager.delete_android("PHONE", "/sdcard/Download/delete-me.txt")
    assert deleted_file == {"deleted": True, "path": "/sdcard/Download/delete-me.txt", "isDirectory": False}
    assert adb.removed[-1] == ("PHONE", "/sdcard/Download/delete-me.txt", False)

    deleted_folder = await manager.delete_android("PHONE", "/sdcard/Download/folder")
    assert deleted_folder["isDirectory"] is True
    assert adb.removed[-1] == ("PHONE", "/sdcard/Download/folder", True)
    assert not any(path.startswith("/sdcard/Download/folder") for path in sync.entries)

    with pytest.raises(TransferValidationError, match="roots cannot be deleted"):
        await manager.delete_android("PHONE", "/sdcard/Download")
    with pytest.raises(TransferValidationError, match="roots cannot be deleted"):
        await manager.delete_android("PHONE", "/storage/1234-ABCD")
    with pytest.raises(TransferValidationError, match="must not contain"):
        await manager.delete_android("PHONE", "/sdcard/Download/../../data")
    with pytest.raises(TransferNotFoundError, match="was not found"):
        await manager.delete_android("PHONE", "/sdcard/Download/missing.txt")


@pytest.mark.asyncio
async def test_recent_pictures_are_normalized_filtered_and_sorted(tmp_path: Path) -> None:
    manager = TransferManager(
        RecentPicturesAdb(),
        FakeSync(),
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
    )  # type: ignore[arg-type]

    entries = await manager.list_recent_pictures("PHONE", limit=50)

    assert [(entry.name, entry.path, entry.size, entry.modified_at) for entry in entries] == [
        ("newer.jpg", "/sdcard/DCIM/Camera/newer.jpg", 20, 300),
        ("older.png", "/sdcard/Pictures/older.png", 10, 100),
    ]
