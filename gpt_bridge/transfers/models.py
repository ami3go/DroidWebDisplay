from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class TransferDirection(StrEnum):
    UPLOAD = "upload"
    DOWNLOAD = "download"


class TransferState(StrEnum):
    QUEUED = "queued"
    PREPARING = "preparing"
    TRANSFERRING = "transferring"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class DuplicatePolicy(StrEnum):
    RENAME = "rename"
    OVERWRITE = "overwrite"
    FAIL = "fail"


@dataclass(frozen=True)
class AndroidEntry:
    name: str
    path: str
    mode: int
    size: int
    modified_at: int
    is_directory: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "mode": self.mode,
            "size": self.size,
            "modifiedAt": self.modified_at,
            "isDirectory": self.is_directory,
        }


@dataclass
class TransferRecord:
    transfer_id: str
    direction: TransferDirection
    serial: str
    source_path: str
    destination_path: str
    filename: str
    state: TransferState = TransferState.QUEUED
    size: int | None = None
    bytes_transferred: int = 0
    speed_bytes_per_second: float = 0.0
    created_at: float = 0.0
    started_at: float | None = None
    ended_at: float | None = None
    retry_count: int = 0
    error: str | None = None
    verification: str | None = None
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.RENAME
    destination_profile: str | None = None
    internal_local_path: str | None = field(default=None, repr=False)
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def progress(self) -> float | None:
        if not self.size or self.size <= 0:
            return None
        return min(1.0, self.bytes_transferred / self.size)

    def add_event(self, timestamp: float, event: str, **details: Any) -> None:
        self.history.append({"timestamp": timestamp, "event": event, **details})
        if len(self.history) > 100:
            del self.history[:-100]

    def to_dict(self, *, include_internal: bool = False) -> dict[str, Any]:
        result = asdict(self)
        result.update(
            {
                "transferId": result.pop("transfer_id"),
                "sourcePath": result.pop("source_path"),
                "destinationPath": result.pop("destination_path"),
                "bytesTransferred": result.pop("bytes_transferred"),
                "speedBytesPerSecond": result.pop("speed_bytes_per_second"),
                "createdAt": result.pop("created_at"),
                "startedAt": result.pop("started_at"),
                "endedAt": result.pop("ended_at"),
                "retryCount": result.pop("retry_count"),
                "duplicatePolicy": result.pop("duplicate_policy"),
                "destinationProfile": result.pop("destination_profile"),
                "progress": self.progress,
            }
        )
        result["direction"] = self.direction.value
        result["state"] = self.state.value
        result["duplicatePolicy"] = self.duplicate_policy.value
        if include_internal:
            result["internalLocalPath"] = result.pop("internal_local_path")
        else:
            result.pop("internal_local_path", None)
        return result
