from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path, PurePosixPath
import secrets
import shutil
import subprocess
import sys
import time
from typing import Any

from droid_web_display.adb.client import AdbClient
from droid_web_display.errors import (
    AdbSyncError,
    TransferCancelledError,
    TransferConflictError,
    TransferError,
    TransferNotFoundError,
    TransferValidationError,
)
from droid_web_display.transfers.adb_sync import AdbSyncClient
from droid_web_display.transfers.models import AndroidEntry, DuplicatePolicy, TransferDirection, TransferRecord, TransferState
from droid_web_display.transfers.paths import join_android_path, normalize_android_path, resolve_duplicate, sanitize_filename


_FINAL_STATES = {TransferState.COMPLETED, TransferState.CANCELLED, TransferState.FAILED, TransferState.INTERRUPTED}
_RETRYABLE_STATES = {TransferState.CANCELLED, TransferState.FAILED, TransferState.INTERRUPTED}
_DISK_FREE_RESERVE = 16 * 1024 * 1024
_MAX_FINAL_RECORDS = 500

# Directories the OS runs code from on login/boot. A file pulled off the phone
# must never land in one of these.
_AUTORUN_DIRECTORY_NAMES = frozenset(
    {
        "autostart",
        "cron.d",
        "cron.daily",
        "cron.hourly",
        "cron.monthly",
        "cron.weekly",
        "init.d",
        "systemd",
        "launchagents",
        "launchdaemons",
        "startup",
        "start menu",
        ".ssh",
        ".gnupg",
    }
)
# Top-level directories owned by the OS, matched directly under the filesystem
# root (POSIX "/", or a Windows drive anchor such as "c:\\").
_SYSTEM_ROOT_NAMES = frozenset(
    {
        "etc",
        "boot",
        "bin",
        "sbin",
        "lib",
        "lib64",
        "usr",
        "proc",
        "sys",
        "var",
        "windows",
        "winnt",
        "program files",
        "program files (x86)",
        "programdata",
        "system volume information",
    }
)


class TransferManager:
    def __init__(
        self,
        adb: AdbClient,
        sync: AdbSyncClient,
        *,
        data_directory: Path,
        destination_profiles: dict[str, Path],
        concurrency: int = 1,
        maximum_queue_length: int = 100,
        maximum_file_size: int = 2 * 1024 * 1024 * 1024,
    ) -> None:
        if not 1 <= concurrency <= 4:
            raise ValueError("transfer concurrency must be in range 1..4")
        self.adb = adb
        self.sync = sync
        self.data_directory = data_directory
        self.upload_spool = data_directory / "upload-spool"
        self.state_file = data_directory / "transfers.json"
        self.allow_custom_destination_paths = bool(getattr(destination_profiles, "allow_custom_paths", True))
        self.destination_profiles = {key: value.resolve() for key, value in destination_profiles.items()}
        self.maximum_queue_length = maximum_queue_length
        self.maximum_file_size = maximum_file_size
        self.maximum_spool_size = maximum_file_size * min(maximum_queue_length, 4)
        self._semaphore = asyncio.Semaphore(concurrency)
        self._records: dict[str, TransferRecord] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._spool_reservations: set[Path] = set()
        self._local_destination_locks: dict[str, asyncio.Lock] = {}
        self._remote_destination_locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._persist_lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self.upload_spool.mkdir(parents=True, exist_ok=True)
        for path in self.destination_profiles.values():
            path.mkdir(parents=True, exist_ok=True)
        await self._load_state()
        self._sweep_orphan_spool_files()
        self._started = True

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        now = time.time()
        for record in self._records.values():
            if record.state not in _FINAL_STATES:
                record.state = TransferState.INTERRUPTED
                record.ended_at = now
                record.error = "bridge service stopped during transfer"
                record.add_event(now, "interrupted", reason="service_shutdown")
        await self._persist()
        self._tasks.clear()
        self._spool_reservations.clear()
        self._local_destination_locks.clear()
        self._remote_destination_locks.clear()
        self._started = False

    def list_records(self) -> list[TransferRecord]:
        values = sorted(self._records.values(), key=lambda item: item.created_at, reverse=True)
        kept: list[TransferRecord] = []
        final_count = 0
        for record in values:
            if record.state in _FINAL_STATES:
                final_count += 1
                if final_count > _MAX_FINAL_RECORDS:
                    self._records.pop(record.transfer_id, None)
                    continue
            kept.append(record)
        return kept

    def get(self, transfer_id: str) -> TransferRecord:
        try:
            return self._records[transfer_id]
        except KeyError as exc:
            raise TransferNotFoundError("transfer not found", details={"transferId": transfer_id}) from exc

    def destination_profile_list(self) -> list[dict[str, str]]:
        return [{"id": key, "path": str(path)} for key, path in sorted(self.destination_profiles.items())]

    def destination_path(self, profile_id: str) -> Path:
        """Return a validated destination profile path without opening it."""
        return self._profile(profile_id)

    def open_destination_profile(self, profile_id: str) -> Path:
        return self._open_local_folder(self._profile(profile_id))

    def open_destination_path(self, destination_path: str) -> Path:
        return self._open_local_folder(self._custom_destination(destination_path))

    def _open_local_folder(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                import os
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            raise TransferError("unable to open destination folder", details={"path": str(path), "error": str(exc)}) from exc
        return path

    async def list_android(self, serial: str, path: str) -> list[AndroidEntry]:
        normalized = normalize_android_path(path)
        entries = await self.sync.list(serial, normalized)
        return [
            AndroidEntry(
                name=entry.name,
                path=normalize_android_path(str(PurePosixPath(normalized) / entry.name)),
                mode=entry.mode,
                size=entry.size,
                modified_at=entry.modified_at,
                is_directory=entry.is_directory,
            )
            for entry in sorted(entries, key=lambda item: (not item.is_directory, item.name.casefold()))
        ]

    def _reserve_spool(self, safe_name: str) -> Path:
        self._check_queue_capacity()
        spool_path = self.upload_spool / f"{secrets.token_urlsafe(12)}-{safe_name}.part"
        self._spool_reservations.add(spool_path)
        return spool_path

    def _release_spool_reservation(self, spool_path: Path) -> None:
        self._spool_reservations.discard(spool_path)

    def _spool_usage(self) -> int:
        total = 0
        for path in self.upload_spool.glob("*.part"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
        return total

    def _check_spool_capacity(self, *, existing_bytes: int, incoming_bytes: int) -> None:
        if existing_bytes + incoming_bytes > self.maximum_spool_size:
            raise TransferValidationError(
                "upload spool capacity exceeded",
                details={"maximumSpoolSize": self.maximum_spool_size},
            )
        free = shutil.disk_usage(self.upload_spool).free
        if free < incoming_bytes + _DISK_FREE_RESERVE:
            raise TransferValidationError(
                "insufficient free disk space for upload spool",
                details={"freeBytes": free, "reserveBytes": _DISK_FREE_RESERVE},
            )

    async def spool_upload(self, filename: str, chunks: Any) -> tuple[Path, int, str]:
        safe_name = sanitize_filename(filename)
        spool_path = self._reserve_spool(safe_name)
        baseline = self._spool_usage()
        total = 0
        try:
            with spool_path.open("wb") as output:
                while True:
                    chunk = await chunks.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self.maximum_file_size:
                        raise TransferValidationError(
                            "file exceeds configured maximum size",
                            details={"maximumFileSize": self.maximum_file_size},
                        )
                    self._check_spool_capacity(existing_bytes=baseline, incoming_bytes=total)
                    output.write(chunk)
        except Exception:
            self._release_spool_reservation(spool_path)
            spool_path.unlink(missing_ok=True)
            raise
        return spool_path, total, safe_name

    async def spool_local_file(self, source_path: Path) -> tuple[Path, int, str]:
        """Copy a watched local file into the managed upload spool.

        Upload workers delete their spool files after verified transfer, so a
        two-way folder monitor must never pass the user's original file to the
        worker. The source is checked before and after copying to avoid
        uploading a file that is still being written.
        """
        source = source_path.resolve()
        if not source.is_file():
            raise TransferValidationError("local sync source is not a regular file", details={"path": str(source)})
        before = source.stat()
        if before.st_size > self.maximum_file_size:
            raise TransferValidationError(
                "file exceeds configured maximum size",
                details={"path": str(source), "maximumFileSize": self.maximum_file_size},
            )
        safe_name = sanitize_filename(source.name)
        spool_path = self._reserve_spool(safe_name)
        try:
            self._check_spool_capacity(existing_bytes=self._spool_usage(), incoming_bytes=before.st_size)
            await asyncio.to_thread(shutil.copyfile, source, spool_path)
            after = source.stat()
            if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                raise TransferConflictError(
                    "local sync source changed while preparing upload",
                    details={"path": str(source)},
                )
            if spool_path.stat().st_size != after.st_size:
                raise TransferError(
                    "local sync spool verification failed",
                    details={"path": str(source), "expected": after.st_size, "actual": spool_path.stat().st_size},
                )
            return spool_path, after.st_size, safe_name
        except Exception:
            self._release_spool_reservation(spool_path)
            spool_path.unlink(missing_ok=True)
            raise

    async def enqueue_upload(
        self,
        *,
        serial: str,
        spool_path: Path,
        original_filename: str,
        size: int,
        destination_directory: str,
        duplicate_policy: DuplicatePolicy = DuplicatePolicy.RENAME,
    ) -> TransferRecord:
        reserved = spool_path in self._spool_reservations
        if reserved:
            self._release_spool_reservation(spool_path)
        try:
            self._check_queue_capacity()
            destination = join_android_path(destination_directory, original_filename)
            record = TransferRecord(
                transfer_id=secrets.token_urlsafe(18),
                direction=TransferDirection.UPLOAD,
                serial=serial,
                source_path=original_filename,
                destination_path=destination,
                filename=sanitize_filename(original_filename),
                size=size,
                created_at=time.time(),
                duplicate_policy=duplicate_policy,
                internal_local_path=str(spool_path),
            )
            record.add_event(record.created_at, "queued")
            await self._register_and_run(record)
            return record
        except Exception:
            spool_path.unlink(missing_ok=True)
            raise

    async def enqueue_download(
        self,
        *,
        serial: str,
        source_path: str,
        destination_profile: str = "default-downloads",
        destination_path: str | None = None,
        duplicate_policy: DuplicatePolicy = DuplicatePolicy.RENAME,
    ) -> TransferRecord:
        self._check_queue_capacity()
        normalized = normalize_android_path(source_path)
        profile_path = self._custom_destination(destination_path) if destination_path else self._profile(destination_profile)
        destination_label = "custom" if destination_path else destination_profile
        filename = sanitize_filename(PurePosixPath(normalized).name)
        # Duplicate resolution belongs in the worker under the destination lock.
        destination = profile_path / filename
        record = TransferRecord(
            transfer_id=secrets.token_urlsafe(18),
            direction=TransferDirection.DOWNLOAD,
            serial=serial,
            source_path=normalized,
            destination_path=str(destination),
            filename=filename,
            created_at=time.time(),
            duplicate_policy=duplicate_policy,
            destination_profile=destination_label,
            internal_local_path=str(destination),
        )
        record.add_event(record.created_at, "queued")
        await self._register_and_run(record)
        return record

    async def cancel(self, transfer_id: str) -> TransferRecord:
        record = self.get(transfer_id)
        if record.state in _FINAL_STATES:
            if record.state == TransferState.CANCELLED:
                return record
            raise TransferConflictError("completed or failed transfer cannot be cancelled", details={"state": record.state.value})
        task = self._tasks.get(transfer_id)
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if record.state != TransferState.CANCELLED:
            await self._mark_cancelled(record)
        return record

    async def retry(self, transfer_id: str) -> TransferRecord:
        record = self.get(transfer_id)
        if record.state not in _RETRYABLE_STATES:
            raise TransferConflictError("transfer is not retryable", details={"state": record.state.value})
        if record.direction == TransferDirection.UPLOAD and (not record.internal_local_path or not Path(record.internal_local_path).is_file()):
            raise TransferConflictError("upload spool file is unavailable; select the source file again")
        record.state = TransferState.QUEUED
        record.bytes_transferred = 0
        record.speed_bytes_per_second = 0.0
        record.started_at = None
        record.ended_at = None
        record.error = None
        record.verification = None
        record.retry_count += 1
        record.add_event(time.time(), "retry_queued", retryCount=record.retry_count)
        await self._persist()
        self._schedule(record)
        return record

    async def _register_and_run(self, record: TransferRecord) -> None:
        self._records[record.transfer_id] = record
        await self._persist()
        self._schedule(record)

    def _schedule(self, record: TransferRecord) -> None:
        task = asyncio.create_task(self._execute(record), name=f"transfer-{record.transfer_id}")
        self._tasks[record.transfer_id] = task
        task.add_done_callback(lambda finished: self._discard_task(record.transfer_id, finished))

    def _discard_task(self, transfer_id: str, finished: asyncio.Task) -> None:
        # A retry can register a new task under the same id before this callback
        # runs; only drop the entry if it still points at the task that ended.
        if self._tasks.get(transfer_id) is finished:
            self._tasks.pop(transfer_id, None)

    def _local_destination_lock(self, path: Path) -> asyncio.Lock:
        return self._local_destination_locks.setdefault(str(path.resolve()), asyncio.Lock())

    def _remote_destination_lock(self, serial: str, path: str) -> asyncio.Lock:
        return self._remote_destination_locks.setdefault((serial, path), asyncio.Lock())

    async def _execute(self, record: TransferRecord) -> None:
        try:
            async with self._semaphore:
                now = time.time()
                record.state = TransferState.PREPARING
                record.started_at = now
                record.add_event(now, "preparing")
                await self._persist()
                await self._require_ready_device(record.serial)
                if record.direction == TransferDirection.UPLOAD:
                    await self._run_upload(record)
                else:
                    await self._run_download(record)
        except (asyncio.CancelledError, TransferCancelledError):
            await self._mark_cancelled(record)
        except Exception as exc:
            record.state = TransferState.FAILED
            record.ended_at = time.time()
            record.error = str(exc)
            record.add_event(record.ended_at, "failed", error=str(exc))
            self._cleanup_partial(record)
            await self._persist()

    async def _run_upload(self, record: TransferRecord) -> None:
        assert record.internal_local_path
        local = Path(record.internal_local_path)
        requested_destination = record.destination_path
        async with self._remote_destination_lock(record.serial, requested_destination):
            destination = await self._resolve_remote_duplicate(
                record.serial,
                requested_destination,
                record.duplicate_policy,
            )
            record.destination_path = destination
            parent = str(PurePosixPath(destination).parent)
            await self.adb.mkdir(record.serial, parent)
            record.state = TransferState.TRANSFERRING
            record.add_event(time.time(), "transferring")
            await self._persist()
            started = time.monotonic()

            async def progress(done: int, total: int | None) -> None:
                record.bytes_transferred = done
                record.size = total or record.size
                elapsed = max(time.monotonic() - started, 0.001)
                record.speed_bytes_per_second = done / elapsed

            await self.sync.push(record.serial, local, destination, progress=progress)
            record.state = TransferState.VERIFYING
            record.add_event(time.time(), "verifying")
            remote = await self.sync.stat(record.serial, destination)
            expected = local.stat().st_size
            if not remote.exists or remote.size != expected:
                raise TransferError(
                    "upload verification failed",
                    details={"expected": expected, "actual": remote.size, "destination": destination},
                )
            record.bytes_transferred = expected
            record.size = expected
            record.verification = "size-match"
            await self._complete(record)

        # The transfer itself is done and verified past this point. Housekeeping
        # failures must not drag the record back out of COMPLETED, or the
        # auto-download monitor will re-queue an upload that already landed.
        media_scan = getattr(self.adb, "media_scan", None)
        if callable(media_scan):
            try:
                await media_scan(record.serial, record.destination_path)
            except Exception as exc:
                record.add_event(time.time(), "media_scan_failed", error=str(exc))
        local.unlink(missing_ok=True)
        record.internal_local_path = None
        await self._persist()

    async def _run_download(self, record: TransferRecord) -> None:
        assert record.internal_local_path
        requested_path = Path(record.internal_local_path)
        requested_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._local_destination_lock(requested_path):
            final_path = resolve_duplicate(requested_path, record.duplicate_policy)
            record.destination_path = str(final_path)
            record.internal_local_path = str(final_path)
            partial = final_path.with_name(final_path.name + f".{record.transfer_id}.part")
            remote = await self.sync.stat(record.serial, record.source_path)
            if not remote.exists or remote.is_directory:
                raise TransferValidationError(
                    "download source is not a regular file",
                    details={"sourcePath": record.source_path},
                )
            if remote.size > self.maximum_file_size:
                raise TransferValidationError(
                    "download exceeds configured maximum size",
                    details={
                        "sourcePath": record.source_path,
                        "size": remote.size,
                        "maximumFileSize": self.maximum_file_size,
                    },
                )
            record.size = remote.size
            record.state = TransferState.TRANSFERRING
            record.add_event(time.time(), "transferring")
            await self._persist()
            started = time.monotonic()

            async def progress(done: int, total: int | None) -> None:
                record.bytes_transferred = done
                record.size = total or record.size
                elapsed = max(time.monotonic() - started, 0.001)
                record.speed_bytes_per_second = done / elapsed

            try:
                await self.sync.pull(record.serial, record.source_path, partial, progress=progress)
                record.state = TransferState.VERIFYING
                record.add_event(time.time(), "verifying")
                if partial.stat().st_size != remote.size:
                    raise TransferError(
                        "download verification failed",
                        details={"expected": remote.size, "actual": partial.stat().st_size},
                    )
                partial.replace(final_path)
            finally:
                partial.unlink(missing_ok=True)
            record.bytes_transferred = remote.size
            record.verification = "size-match"
            await self._complete(record)

    async def _complete(self, record: TransferRecord) -> None:
        record.state = TransferState.COMPLETED
        record.ended_at = time.time()
        record.speed_bytes_per_second = 0.0
        record.add_event(record.ended_at, "completed", verification=record.verification)
        await self._persist()

    async def _mark_cancelled(self, record: TransferRecord) -> None:
        record.state = TransferState.CANCELLED
        record.ended_at = time.time()
        record.error = None
        record.speed_bytes_per_second = 0.0
        record.add_event(record.ended_at, "cancelled")
        self._cleanup_partial(record)
        await self._persist()

    def _cleanup_partial(self, record: TransferRecord) -> None:
        if record.direction != TransferDirection.DOWNLOAD or not record.internal_local_path:
            return
        final_path = Path(record.internal_local_path)
        final_path.with_name(final_path.name + f".{record.transfer_id}.part").unlink(missing_ok=True)

    async def _resolve_remote_duplicate(self, serial: str, path: str, policy: DuplicatePolicy) -> str:
        stat = await self.sync.stat(serial, path)
        if not stat.exists or policy == DuplicatePolicy.OVERWRITE:
            return path
        if policy == DuplicatePolicy.FAIL:
            raise TransferConflictError("Android destination already exists", details={"path": path})
        pure = PurePosixPath(path)
        stem, suffix = pure.stem, pure.suffix
        for index in range(1, 10_000):
            candidate = str(pure.with_name(f"{stem} ({index}){suffix}"))
            if not (await self.sync.stat(serial, candidate)).exists:
                return candidate
        raise TransferConflictError("unable to resolve duplicate Android filename", details={"path": path})

    async def _require_ready_device(self, serial: str) -> None:
        state = await self.adb.get_state(serial)
        if state != "device":
            raise TransferError("Android device is not ready", details={"serial": serial, "state": state})

    def _check_queue_capacity(self) -> None:
        active = sum(record.state not in _FINAL_STATES for record in self._records.values())
        active += len(self._spool_reservations)
        if active >= self.maximum_queue_length:
            raise TransferConflictError("transfer queue is full", details={"maximumQueueLength": self.maximum_queue_length})

    def _sweep_orphan_spool_files(self) -> None:
        referenced = {
            Path(record.internal_local_path).resolve()
            for record in self._records.values()
            if record.direction == TransferDirection.UPLOAD and record.internal_local_path
        }
        for path in self.upload_spool.glob("*.part"):
            try:
                if path.resolve() not in referenced:
                    path.unlink(missing_ok=True)
            except OSError:
                continue

    def _profile(self, profile_id: str) -> Path:
        try:
            return self.destination_profiles[profile_id]
        except KeyError as exc:
            raise TransferValidationError(
                "unknown destination profile",
                details={"destinationProfile": profile_id, "available": sorted(self.destination_profiles)},
            ) from exc

    def _custom_destination(self, destination_path: str) -> Path:
        raw = Path(destination_path).expanduser()
        if not raw.is_absolute():
            raise TransferValidationError("custom destination must be an absolute PC path", details={"destinationPath": destination_path})
        path = raw.resolve()
        if path.exists() and not path.is_dir():
            raise TransferValidationError("custom destination is not a folder", details={"destinationPath": str(path)})
        if not self.allow_custom_destination_paths:
            self._assert_within_destination_profile(path)
        self._assert_destination_allowed(path)
        return path

    def _assert_within_destination_profile(self, path: Path) -> None:
        approved = tuple(self.destination_profiles.values())
        if any(path == root or root in path.parents for root in approved):
            return
        raise TransferValidationError(
            "custom destination must be inside an approved destination profile",
            details={
                "destinationPath": str(path),
                "approvedRoots": [str(root) for root in approved],
            },
        )

    def _assert_destination_allowed(self, path: Path) -> None:
        """Reject destinations that would turn a transfer into code execution.

        Custom absolute folders are a PC-local convenience. LAN mode confines
        them to approved profiles before these defense-in-depth checks run.
        """
        lowered_parts = tuple(part.lower() for part in path.parts)
        blocked = set(lowered_parts) & _AUTORUN_DIRECTORY_NAMES
        if blocked:
            raise TransferValidationError(
                "custom destination is a startup or system folder",
                details={"destinationPath": str(path), "blockedComponent": min(blocked)},
            )
        # parts[0] is the filesystem anchor: "/" on POSIX, a drive root such as
        # "C:\\" on Windows. Anything named directly beneath it is OS-owned.
        if len(lowered_parts) >= 2 and lowered_parts[1] in _SYSTEM_ROOT_NAMES:
            raise TransferValidationError(
                "custom destination is a system folder",
                details={"destinationPath": str(path), "blockedComponent": lowered_parts[1]},
            )

    async def _load_state(self) -> None:
        if not self.state_file.is_file():
            return
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        now = time.time()
        for item in payload.get("transfers", []):
            try:
                record = TransferRecord(
                    transfer_id=item["transferId"],
                    direction=TransferDirection(item["direction"]),
                    serial=item["serial"],
                    source_path=item["sourcePath"],
                    destination_path=item["destinationPath"],
                    filename=item["filename"],
                    state=TransferState(item["state"]),
                    size=item.get("size"),
                    bytes_transferred=item.get("bytesTransferred", 0),
                    speed_bytes_per_second=0.0,
                    created_at=item.get("createdAt", now),
                    started_at=item.get("startedAt"),
                    ended_at=item.get("endedAt"),
                    retry_count=item.get("retryCount", 0),
                    error=item.get("error"),
                    verification=item.get("verification"),
                    duplicate_policy=DuplicatePolicy(item.get("duplicatePolicy", "rename")),
                    destination_profile=item.get("destinationProfile"),
                    internal_local_path=item.get("internalLocalPath"),
                    history=item.get("history", []),
                )
            except (KeyError, ValueError, TypeError):
                continue
            if record.state not in _FINAL_STATES:
                record.state = TransferState.INTERRUPTED
                record.ended_at = now
                record.error = "bridge restarted before transfer completed"
                record.add_event(now, "interrupted", reason="service_restart")
            self._records[record.transfer_id] = record
        self.list_records()

    async def _persist(self) -> None:
        self.data_directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 1,
            "transfers": [record.to_dict(include_internal=True) for record in self.list_records()],
        }
        async with self._persist_lock:
            temporary = self.state_file.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self.state_file)
