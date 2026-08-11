from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import time
from typing import Any

from gpt_bridge.adb.client import AdbClient
from gpt_bridge.errors import TransferValidationError
from gpt_bridge.transfers.manager import TransferManager
from gpt_bridge.transfers.models import DuplicatePolicy, TransferState
from gpt_bridge.transfers.paths import normalize_android_path

_PARTIAL_SUFFIXES = (".part", ".partial", ".crdownload", ".download", ".tmp", ".temp")
_FINAL_TRANSFER_STATES = {
    TransferState.COMPLETED,
    TransferState.CANCELLED,
    TransferState.FAILED,
    TransferState.INTERRUPTED,
}


@dataclass(frozen=True)
class AutoDownloadConfig:
    """Configuration for the bidirectional watched-folder service.

    ``enabled`` retains the original Android-to-PC behavior. The optional
    ``pc_to_android_enabled`` direction watches the selected PC destination
    profile and uploads stable new or modified files into ``source_path``.
    Both directions are disabled by default.
    """

    enabled: bool = False
    pc_to_android_enabled: bool = False
    serial: str | None = None
    source_path: str = "/sdcard/Download"
    destination_profile: str = "default-downloads"
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.RENAME
    upload_duplicate_policy: DuplicatePolicy = DuplicatePolicy.OVERWRITE
    scan_interval_seconds: float = 2.0
    stability_seconds: float = 3.0
    stability_observations: int = 3
    include_existing: bool = False
    include_existing_pc: bool = False
    delete_after_verified: bool = False

    def validate(self) -> "AutoDownloadConfig":
        source = normalize_android_path(self.source_path)
        if (self.enabled or self.pc_to_android_enabled) and not self.serial:
            raise TransferValidationError("automatic folder sync requires an Android device serial")
        if not 1.0 <= self.scan_interval_seconds <= 60.0:
            raise TransferValidationError("scan interval must be in range 1..60 seconds")
        if not 1.0 <= self.stability_seconds <= 300.0:
            raise TransferValidationError("stability duration must be in range 1..300 seconds")
        if not 2 <= self.stability_observations <= 20:
            raise TransferValidationError("stability observations must be in range 2..20")
        return AutoDownloadConfig(
            enabled=self.enabled,
            pc_to_android_enabled=self.pc_to_android_enabled,
            serial=self.serial,
            source_path=source,
            destination_profile=self.destination_profile,
            duplicate_policy=self.duplicate_policy,
            upload_duplicate_policy=self.upload_duplicate_policy,
            scan_interval_seconds=float(self.scan_interval_seconds),
            stability_seconds=float(self.stability_seconds),
            stability_observations=int(self.stability_observations),
            include_existing=self.include_existing,
            include_existing_pc=self.include_existing_pc,
            delete_after_verified=self.delete_after_verified,
        )

    @property
    def active(self) -> bool:
        return self.enabled or self.pc_to_android_enabled

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "pcToAndroidEnabled": self.pc_to_android_enabled,
            "serial": self.serial,
            "sourcePath": self.source_path,
            "destinationProfile": self.destination_profile,
            "duplicatePolicy": self.duplicate_policy.value,
            "uploadDuplicatePolicy": self.upload_duplicate_policy.value,
            "scanIntervalSeconds": self.scan_interval_seconds,
            "stabilitySeconds": self.stability_seconds,
            "stabilityObservations": self.stability_observations,
            "includeExisting": self.include_existing,
            "includeExistingPc": self.include_existing_pc,
            "deleteAfterVerified": self.delete_after_verified,
        }


@dataclass
class ObservedFile:
    path: str
    size: int
    modified_at: int
    fingerprint: str
    first_seen_at: float
    last_changed_at: float
    stable_observations: int = 1
    status: str = "pending"
    transfer_id: str | None = None
    retry_count: int = 0
    next_retry_at: float = 0.0
    local_destination: str | None = None
    deletion_result: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "modifiedAt": self.modified_at,
            "fingerprint": self.fingerprint,
            "firstSeenAt": self.first_seen_at,
            "lastChangedAt": self.last_changed_at,
            "stableObservations": self.stable_observations,
            "status": self.status,
            "transferId": self.transfer_id,
            "retryCount": self.retry_count,
            "nextRetryAt": self.next_retry_at,
            "localDestination": self.local_destination,
            "deletionResult": self.deletion_result,
            "error": self.error,
        }


@dataclass
class ObservedLocalFile:
    path: str
    size: int
    modified_ns: int
    fingerprint: str
    first_seen_at: float
    last_changed_at: float
    stable_observations: int = 1
    status: str = "pending"
    transfer_id: str | None = None
    retry_count: int = 0
    next_retry_at: float = 0.0
    remote_destination: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "modifiedNs": self.modified_ns,
            "fingerprint": self.fingerprint,
            "firstSeenAt": self.first_seen_at,
            "lastChangedAt": self.last_changed_at,
            "stableObservations": self.stable_observations,
            "status": self.status,
            "transferId": self.transfer_id,
            "retryCount": self.retry_count,
            "nextRetryAt": self.next_retry_at,
            "remoteDestination": self.remote_destination,
            "error": self.error,
        }


@dataclass
class AutoDownloadRuntime:
    state: str = "disabled"
    baseline_initialized: bool = False
    pc_baseline_initialized: bool = False
    last_scan_at: float | None = None
    last_success_at: float | None = None
    last_error: str | None = None
    scan_count: int = 0
    files_seen: int = 0
    pc_files_seen: int = 0
    downloads_queued: int = 0
    downloads_completed: int = 0
    uploads_queued: int = 0
    uploads_completed: int = 0
    deletions_completed: int = 0
    notifications: list[dict[str, Any]] = field(default_factory=list)

    def notify(self, event: str, message: str, **details: Any) -> None:
        self.notifications.append({"timestamp": time.time(), "event": event, "message": message, **details})
        if len(self.notifications) > 100:
            del self.notifications[:-100]


class AutoDownloadMonitor:
    """Persistent, non-recursive Android/PC watched-folder synchronizer.

    Android-to-PC uses structured ADB Sync LIST/STAT and the existing verified
    download queue. PC-to-Android watches the selected destination profile,
    copies stable files into the managed upload spool, then uses the same ADB
    Sync upload queue. Generated downloads/uploads are fingerprinted on both
    sides so the two directions do not bounce the same file back and forth.
    """

    def __init__(
        self,
        adb: AdbClient,
        transfers: TransferManager,
        *,
        data_directory: Path,
    ) -> None:
        self.adb = adb
        self.transfers = transfers
        self.data_directory = data_directory
        self.state_file = data_directory / "auto-download-monitor.json"
        self.config = AutoDownloadConfig()
        self.runtime = AutoDownloadRuntime()
        self._observed: dict[str, ObservedFile] = {}
        self._local_observed: dict[str, ObservedLocalFile] = {}
        self._processed: dict[str, float] = {}
        self._processed_local: dict[str, float] = {}
        self._task: asyncio.Task[None] | None = None
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self.data_directory.mkdir(parents=True, exist_ok=True)
        await self._load()
        self._started = True
        self._task = asyncio.create_task(self._run(), name="automatic-folder-sync")

    async def close(self) -> None:
        task = self._task
        self._task = None
        self._started = False
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self._persist()

    async def configure(self, config: AutoDownloadConfig) -> dict[str, Any]:
        validated = config.validate()
        self.transfers.destination_path(validated.destination_profile)
        async with self._lock:
            remote_changed = (
                validated.serial != self.config.serial
                or validated.source_path != self.config.source_path
                or validated.include_existing != self.config.include_existing
            )
            local_changed = (
                validated.serial != self.config.serial
                or validated.source_path != self.config.source_path
                or validated.destination_profile != self.config.destination_profile
                or validated.include_existing_pc != self.config.include_existing_pc
            )
            self.config = validated
            if remote_changed:
                self.runtime.baseline_initialized = False
                self._observed.clear()
            if local_changed:
                self.runtime.pc_baseline_initialized = False
                self._local_observed.clear()
            self.runtime.state = "watching" if validated.active else "disabled"
            self.runtime.last_error = None
            await self._persist_unlocked()
        self._wake.set()
        return self.snapshot()

    async def scan_now(self) -> dict[str, Any]:
        await self._scan_once(force=True)
        return self.snapshot()

    async def clear_history(self) -> dict[str, Any]:
        async with self._lock:
            self._observed.clear()
            self._local_observed.clear()
            self._processed.clear()
            self._processed_local.clear()
            self.runtime.baseline_initialized = False
            self.runtime.pc_baseline_initialized = False
            self.runtime.notifications.clear()
            self.runtime.files_seen = 0
            self.runtime.pc_files_seen = 0
            self.runtime.downloads_queued = 0
            self.runtime.downloads_completed = 0
            self.runtime.uploads_queued = 0
            self.runtime.uploads_completed = 0
            self.runtime.deletions_completed = 0
            await self._persist_unlocked()
        self._wake.set()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        files = sorted(self._observed.values(), key=lambda item: item.last_changed_at, reverse=True)
        local_files = sorted(self._local_observed.values(), key=lambda item: item.last_changed_at, reverse=True)
        return {
            "schemaVersion": 2,
            "config": self.config.to_dict(),
            "runtime": {
                **asdict(self.runtime),
                "baselineInitialized": self.runtime.baseline_initialized,
                "pcBaselineInitialized": self.runtime.pc_baseline_initialized,
                "lastScanAt": self.runtime.last_scan_at,
                "lastSuccessAt": self.runtime.last_success_at,
                "lastError": self.runtime.last_error,
                "scanCount": self.runtime.scan_count,
                "filesSeen": self.runtime.files_seen,
                "pcFilesSeen": self.runtime.pc_files_seen,
                "downloadsQueued": self.runtime.downloads_queued,
                "downloadsCompleted": self.runtime.downloads_completed,
                "uploadsQueued": self.runtime.uploads_queued,
                "uploadsCompleted": self.runtime.uploads_completed,
                "deletionsCompleted": self.runtime.deletions_completed,
            },
            "files": [item.to_dict() for item in files[:200]],
            "localFiles": [item.to_dict() for item in local_files[:200]],
            "processedFingerprints": len(self._processed),
            "processedPcFingerprints": len(self._processed_local),
        }

    async def _run(self) -> None:
        while True:
            try:
                if self.config.active:
                    await self._scan_once()
                timeout = self.config.scan_interval_seconds if self.config.active else 30.0
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=timeout)
                    self._wake.clear()
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # monitor failures must not terminate the bridge
                self.runtime.state = "error"
                self.runtime.last_error = str(exc)
                self.runtime.notify("monitor-error", str(exc))
                await self._persist()
                await asyncio.sleep(min(max(self.config.scan_interval_seconds, 1.0), 10.0))

    async def _scan_once(self, *, force: bool = False) -> None:
        config = self.config
        if not config.active and not force:
            return
        if not config.serial:
            if force:
                raise TransferValidationError("select a device before scanning")
            return
        now = time.time()
        async with self._lock:
            self.runtime.state = "scanning"
            self.runtime.last_scan_at = now
            self.runtime.scan_count += 1
        try:
            await self._reconcile_transfers(now)
            if config.enabled or force:
                await self._scan_android(now)
            if config.pc_to_android_enabled:
                await self._scan_pc(now)
            async with self._lock:
                self.runtime.state = "watching" if config.active else "disabled"
                self.runtime.last_success_at = now
                self.runtime.last_error = None
                self._trim_processed()
                await self._persist_unlocked()
        except Exception as exc:
            async with self._lock:
                self.runtime.state = "error"
                self.runtime.last_error = str(exc)
                self.runtime.notify("scan-failed", str(exc))
                await self._persist_unlocked()
            if force:
                raise

    async def _scan_android(self, now: float) -> None:
        config = self.config
        entries = await self.transfers.list_android(config.serial or "", config.source_path)
        files = [entry for entry in entries if not entry.is_directory and not self._ignored(entry.name)]
        async with self._lock:
            self.runtime.files_seen = len(files)
            if not self.runtime.baseline_initialized and not config.include_existing:
                for entry in files:
                    fingerprint = self._fingerprint(entry.path, entry.size, entry.modified_at)
                    self._processed[fingerprint] = now
                    self._observed[entry.path] = ObservedFile(
                        path=entry.path,
                        size=entry.size,
                        modified_at=entry.modified_at,
                        fingerprint=fingerprint,
                        first_seen_at=now,
                        last_changed_at=now,
                        stable_observations=config.stability_observations,
                        status="baseline",
                    )
                self.runtime.baseline_initialized = True
                self.runtime.notify("baseline-created", f"Baselined {len(files)} existing Android file(s)")
                return
            self.runtime.baseline_initialized = True

        present_paths = {entry.path for entry in files}
        for entry in files:
            await self._observe_android_entry(entry.path, entry.name, entry.size, entry.modified_at, now)

        async with self._lock:
            for path, observed in list(self._observed.items()):
                if path not in present_paths and observed.status in {"pending", "baseline"}:
                    observed.status = "disappeared"

    async def _scan_pc(self, now: float) -> None:
        config = self.config
        root = self.transfers.destination_path(config.destination_profile)
        root.mkdir(parents=True, exist_ok=True)
        files: list[tuple[Path, int, int]] = []
        for path in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
            if not path.is_file() or self._ignored(path.name):
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append((path.resolve(), stat.st_size, stat.st_mtime_ns))

        async with self._lock:
            self.runtime.pc_files_seen = len(files)
            if not self.runtime.pc_baseline_initialized and not config.include_existing_pc:
                for path, size, modified_ns in files:
                    fingerprint = self._local_fingerprint(path, size, modified_ns)
                    self._processed_local[fingerprint] = now
                    self._local_observed[str(path)] = ObservedLocalFile(
                        path=str(path),
                        size=size,
                        modified_ns=modified_ns,
                        fingerprint=fingerprint,
                        first_seen_at=now,
                        last_changed_at=now,
                        stable_observations=config.stability_observations,
                        status="baseline",
                    )
                self.runtime.pc_baseline_initialized = True
                self.runtime.notify("pc-baseline-created", f"Baselined {len(files)} existing PC file(s)")
                return
            self.runtime.pc_baseline_initialized = True

        present_paths = {str(item[0]) for item in files}
        for path, size, modified_ns in files:
            await self._observe_pc_entry(path, size, modified_ns, now)

        async with self._lock:
            for path, observed in list(self._local_observed.items()):
                if path not in present_paths and observed.status in {"pending", "baseline"}:
                    observed.status = "disappeared"

    async def _observe_android_entry(self, path: str, name: str, size: int, modified_at: int, now: float) -> None:
        config = self.config
        fingerprint = self._fingerprint(path, size, modified_at)
        async with self._lock:
            observed = self._observed.get(path)
            if observed is None or observed.fingerprint != fingerprint:
                observed = ObservedFile(
                    path=path,
                    size=size,
                    modified_at=modified_at,
                    fingerprint=fingerprint,
                    first_seen_at=now,
                    last_changed_at=now,
                )
                self._observed[path] = observed
            else:
                observed.stable_observations += 1
                observed.size = size
                observed.modified_at = modified_at
            if fingerprint in self._processed:
                if observed.status not in {"completed", "deleted", "baseline", "uploaded-from-pc"}:
                    observed.status = "processed"
                return
            if observed.transfer_id:
                return
            stable = (
                observed.stable_observations >= config.stability_observations
                and now - observed.last_changed_at >= config.stability_seconds
            )
            if not stable or now < observed.next_retry_at:
                observed.status = "pending"
                return
            observed.status = "queueing"

        try:
            record = await self.transfers.enqueue_download(
                serial=config.serial or "",
                source_path=path,
                destination_profile=config.destination_profile,
                duplicate_policy=config.duplicate_policy,
            )
        except Exception as exc:
            async with self._lock:
                observed = self._observed[path]
                observed.status = "failed"
                observed.error = str(exc)
                observed.retry_count += 1
                observed.next_retry_at = now + self._retry_delay(observed.retry_count)
                self.runtime.notify("queue-failed", f"Could not queue Android file {name}", path=path, error=str(exc))
            return

        async with self._lock:
            observed = self._observed[path]
            observed.status = "queued"
            observed.transfer_id = record.transfer_id
            observed.error = None
            self.runtime.downloads_queued += 1
            self.runtime.notify("download-queued", f"Queued Android → PC: {name}", path=path, transferId=record.transfer_id)

    async def _observe_pc_entry(self, path: Path, size: int, modified_ns: int, now: float) -> None:
        config = self.config
        key = str(path)
        fingerprint = self._local_fingerprint(path, size, modified_ns)
        async with self._lock:
            observed = self._local_observed.get(key)
            if observed is None or observed.fingerprint != fingerprint:
                observed = ObservedLocalFile(
                    path=key,
                    size=size,
                    modified_ns=modified_ns,
                    fingerprint=fingerprint,
                    first_seen_at=now,
                    last_changed_at=now,
                )
                self._local_observed[key] = observed
            else:
                observed.stable_observations += 1
                observed.size = size
                observed.modified_ns = modified_ns
            if fingerprint in self._processed_local:
                if observed.status not in {"completed", "baseline", "downloaded-from-android"}:
                    observed.status = "processed"
                return
            if observed.transfer_id:
                return
            stable = (
                observed.stable_observations >= config.stability_observations
                and now - observed.last_changed_at >= config.stability_seconds
            )
            if not stable or now < observed.next_retry_at:
                observed.status = "pending"
                return
            observed.status = "queueing"

        spool: Path | None = None
        try:
            spool, upload_size, safe_name = await self.transfers.spool_local_file(path)
            record = await self.transfers.enqueue_upload(
                serial=config.serial or "",
                spool_path=spool,
                original_filename=safe_name,
                size=upload_size,
                destination_directory=config.source_path,
                duplicate_policy=config.upload_duplicate_policy,
            )
        except Exception as exc:
            if spool:
                spool.unlink(missing_ok=True)
            async with self._lock:
                observed = self._local_observed[key]
                observed.status = "failed"
                observed.error = str(exc)
                observed.retry_count += 1
                observed.next_retry_at = now + self._retry_delay(observed.retry_count)
                self.runtime.notify("upload-queue-failed", f"Could not queue PC file {path.name}", path=key, error=str(exc))
            return

        async with self._lock:
            observed = self._local_observed[key]
            observed.status = "queued"
            observed.transfer_id = record.transfer_id
            observed.error = None
            self.runtime.uploads_queued += 1
            self.runtime.notify("upload-queued", f"Queued PC → Android: {path.name}", path=key, transferId=record.transfer_id)

    async def _reconcile_transfers(self, now: float) -> None:
        await self._reconcile_downloads(now)
        await self._reconcile_uploads(now)

    async def _reconcile_downloads(self, now: float) -> None:
        config = self.config
        pending = [item for item in self._observed.values() if item.transfer_id]
        for observed in pending:
            try:
                record = self.transfers.get(observed.transfer_id or "")
            except Exception:
                continue
            if record.state not in _FINAL_TRANSFER_STATES:
                observed.status = record.state.value
                continue
            if record.state == TransferState.COMPLETED and record.verification == "size-match":
                if observed.fingerprint not in self._processed:
                    self._processed[observed.fingerprint] = now
                    self.runtime.downloads_completed += 1
                    self.runtime.notify(
                        "download-completed",
                        f"Downloaded Android → PC: {record.filename}",
                        path=observed.path,
                        destination=record.destination_path,
                        transferId=record.transfer_id,
                    )
                observed.status = "completed"
                observed.local_destination = record.destination_path
                observed.error = None
                self._mark_local_processed(Path(record.destination_path), now, "downloaded-from-android")
                if config.delete_after_verified and observed.deletion_result is None:
                    await self._delete_verified_remote(observed)
            else:
                observed.status = "failed"
                observed.error = record.error or f"transfer ended as {record.state.value}"
                observed.transfer_id = None
                observed.retry_count += 1
                observed.next_retry_at = now + self._retry_delay(observed.retry_count)
                self.runtime.notify(
                    "download-failed",
                    f"Automatic Android → PC download failed for {record.filename}",
                    path=observed.path,
                    error=observed.error,
                )

    async def _reconcile_uploads(self, now: float) -> None:
        config = self.config
        pending = [item for item in self._local_observed.values() if item.transfer_id]
        for observed in pending:
            try:
                record = self.transfers.get(observed.transfer_id or "")
            except Exception:
                continue
            if record.state not in _FINAL_TRANSFER_STATES:
                observed.status = record.state.value
                continue
            if record.state == TransferState.COMPLETED and record.verification == "size-match":
                if observed.fingerprint not in self._processed_local:
                    self._processed_local[observed.fingerprint] = now
                    self.runtime.uploads_completed += 1
                    self.runtime.notify(
                        "upload-completed",
                        f"Uploaded PC → Android: {record.filename}",
                        path=observed.path,
                        destination=record.destination_path,
                        transferId=record.transfer_id,
                    )
                observed.status = "completed"
                observed.remote_destination = record.destination_path
                observed.error = None
                remote = await self.transfers.sync.stat(config.serial or "", record.destination_path)
                if remote.exists and not remote.is_directory:
                    fingerprint = self._fingerprint(record.destination_path, remote.size, remote.modified_at)
                    self._processed[fingerprint] = now
                    self._observed[record.destination_path] = ObservedFile(
                        path=record.destination_path,
                        size=remote.size,
                        modified_at=remote.modified_at,
                        fingerprint=fingerprint,
                        first_seen_at=now,
                        last_changed_at=now,
                        stable_observations=config.stability_observations,
                        status="uploaded-from-pc",
                    )
            else:
                observed.status = "failed"
                observed.error = record.error or f"transfer ended as {record.state.value}"
                observed.transfer_id = None
                observed.retry_count += 1
                observed.next_retry_at = now + self._retry_delay(observed.retry_count)
                self.runtime.notify(
                    "upload-failed",
                    f"Automatic PC → Android upload failed for {record.filename}",
                    path=observed.path,
                    error=observed.error,
                )

    def _mark_local_processed(self, path: Path, now: float, status: str) -> None:
        try:
            resolved = path.resolve()
            stat = resolved.stat()
        except OSError:
            return
        fingerprint = self._local_fingerprint(resolved, stat.st_size, stat.st_mtime_ns)
        self._processed_local[fingerprint] = now
        self._local_observed[str(resolved)] = ObservedLocalFile(
            path=str(resolved),
            size=stat.st_size,
            modified_ns=stat.st_mtime_ns,
            fingerprint=fingerprint,
            first_seen_at=now,
            last_changed_at=now,
            stable_observations=self.config.stability_observations,
            status=status,
        )

    async def _delete_verified_remote(self, observed: ObservedFile) -> None:
        config = self.config
        if not config.serial:
            return
        try:
            await self.adb.remove_file(config.serial, observed.path)
            remote = await self.transfers.sync.stat(config.serial, observed.path)
            if remote.exists:
                raise RuntimeError("Android file still exists after deletion request")
            observed.status = "deleted"
            observed.deletion_result = "verified-absent"
            self.runtime.deletions_completed += 1
            self.runtime.notify("remote-deleted", f"Deleted verified Android source {observed.path}", path=observed.path)
        except Exception as exc:
            observed.deletion_result = "failed"
            observed.error = f"download completed, but source deletion failed: {exc}"
            self.runtime.notify("delete-failed", observed.error, path=observed.path)

    async def _load(self) -> None:
        if not self.state_file.is_file():
            return
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
            config_data = payload.get("config", {})
            self.config = AutoDownloadConfig(
                enabled=bool(config_data.get("enabled", False)),
                pc_to_android_enabled=bool(config_data.get("pcToAndroidEnabled", False)),
                serial=config_data.get("serial"),
                source_path=config_data.get("sourcePath", "/sdcard/Download"),
                destination_profile=config_data.get("destinationProfile", "default-downloads"),
                duplicate_policy=DuplicatePolicy(config_data.get("duplicatePolicy", "rename")),
                upload_duplicate_policy=DuplicatePolicy(config_data.get("uploadDuplicatePolicy", "overwrite")),
                scan_interval_seconds=float(config_data.get("scanIntervalSeconds", 2.0)),
                stability_seconds=float(config_data.get("stabilitySeconds", 3.0)),
                stability_observations=int(config_data.get("stabilityObservations", 3)),
                include_existing=bool(config_data.get("includeExisting", False)),
                include_existing_pc=bool(config_data.get("includeExistingPc", False)),
                delete_after_verified=bool(config_data.get("deleteAfterVerified", False)),
            ).validate()
            runtime_data = payload.get("runtime", {})
            self.runtime = AutoDownloadRuntime(
                state="watching" if self.config.active else "disabled",
                baseline_initialized=bool(runtime_data.get("baselineInitialized", False)),
                pc_baseline_initialized=bool(runtime_data.get("pcBaselineInitialized", False)),
                last_scan_at=runtime_data.get("lastScanAt"),
                last_success_at=runtime_data.get("lastSuccessAt"),
                last_error=runtime_data.get("lastError"),
                scan_count=int(runtime_data.get("scanCount", 0)),
                files_seen=int(runtime_data.get("filesSeen", 0)),
                pc_files_seen=int(runtime_data.get("pcFilesSeen", 0)),
                downloads_queued=int(runtime_data.get("downloadsQueued", 0)),
                downloads_completed=int(runtime_data.get("downloadsCompleted", 0)),
                uploads_queued=int(runtime_data.get("uploadsQueued", 0)),
                uploads_completed=int(runtime_data.get("uploadsCompleted", 0)),
                deletions_completed=int(runtime_data.get("deletionsCompleted", 0)),
                notifications=list(runtime_data.get("notifications", []))[-100:],
            )
            self._processed = {str(key): float(value) for key, value in payload.get("processed", {}).items()}
            self._processed_local = {str(key): float(value) for key, value in payload.get("processedPc", {}).items()}
            for item in payload.get("files", []):
                observed = ObservedFile(
                    path=item["path"],
                    size=int(item.get("size", 0)),
                    modified_at=int(item.get("modifiedAt", 0)),
                    fingerprint=item["fingerprint"],
                    first_seen_at=float(item.get("firstSeenAt", time.time())),
                    last_changed_at=float(item.get("lastChangedAt", time.time())),
                    stable_observations=int(item.get("stableObservations", 1)),
                    status=item.get("status", "pending"),
                    transfer_id=item.get("transferId"),
                    retry_count=int(item.get("retryCount", 0)),
                    next_retry_at=float(item.get("nextRetryAt", 0.0)),
                    local_destination=item.get("localDestination"),
                    deletion_result=item.get("deletionResult"),
                    error=item.get("error"),
                )
                self._observed[observed.path] = observed
            for item in payload.get("localFiles", []):
                observed = ObservedLocalFile(
                    path=item["path"],
                    size=int(item.get("size", 0)),
                    modified_ns=int(item.get("modifiedNs", 0)),
                    fingerprint=item["fingerprint"],
                    first_seen_at=float(item.get("firstSeenAt", time.time())),
                    last_changed_at=float(item.get("lastChangedAt", time.time())),
                    stable_observations=int(item.get("stableObservations", 1)),
                    status=item.get("status", "pending"),
                    transfer_id=item.get("transferId"),
                    retry_count=int(item.get("retryCount", 0)),
                    next_retry_at=float(item.get("nextRetryAt", 0.0)),
                    remote_destination=item.get("remoteDestination"),
                    error=item.get("error"),
                )
                self._local_observed[observed.path] = observed
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.config = AutoDownloadConfig()
            self.runtime = AutoDownloadRuntime(last_error="monitor state could not be loaded; reset to disabled")
            self._observed.clear()
            self._local_observed.clear()
            self._processed.clear()
            self._processed_local.clear()

    async def _persist(self) -> None:
        async with self._lock:
            await self._persist_unlocked()

    async def _persist_unlocked(self) -> None:
        self.data_directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "schemaVersion": 2,
            "config": self.config.to_dict(),
            "runtime": {
                "state": self.runtime.state,
                "baselineInitialized": self.runtime.baseline_initialized,
                "pcBaselineInitialized": self.runtime.pc_baseline_initialized,
                "lastScanAt": self.runtime.last_scan_at,
                "lastSuccessAt": self.runtime.last_success_at,
                "lastError": self.runtime.last_error,
                "scanCount": self.runtime.scan_count,
                "filesSeen": self.runtime.files_seen,
                "pcFilesSeen": self.runtime.pc_files_seen,
                "downloadsQueued": self.runtime.downloads_queued,
                "downloadsCompleted": self.runtime.downloads_completed,
                "uploadsQueued": self.runtime.uploads_queued,
                "uploadsCompleted": self.runtime.uploads_completed,
                "deletionsCompleted": self.runtime.deletions_completed,
                "notifications": self.runtime.notifications[-100:],
            },
            "processed": self._processed,
            "processedPc": self._processed_local,
            "files": [item.to_dict() for item in self._observed.values()],
            "localFiles": [item.to_dict() for item in self._local_observed.values()],
        }
        temporary = self.state_file.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.state_file)

    def _trim_processed(self) -> None:
        if len(self._processed) > 5000:
            newest = sorted(self._processed.items(), key=lambda item: item[1], reverse=True)[:5000]
            self._processed = dict(newest)
        if len(self._processed_local) > 5000:
            newest_local = sorted(self._processed_local.items(), key=lambda item: item[1], reverse=True)[:5000]
            self._processed_local = dict(newest_local)

    @staticmethod
    def _fingerprint(path: str, size: int, modified_at: int) -> str:
        return f"{path}\0{size}\0{modified_at}"

    @staticmethod
    def _local_fingerprint(path: Path, size: int, modified_ns: int) -> str:
        return f"{path}\0{size}\0{modified_ns}"

    @staticmethod
    def _retry_delay(retry_count: int) -> float:
        return min(300.0, 15.0 * (2 ** min(retry_count, 4)))

    @staticmethod
    def _ignored(name: str) -> bool:
        lowered = name.casefold()
        return lowered.startswith(".") or lowered.endswith(_PARTIAL_SUFFIXES)
