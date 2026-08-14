from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StorageUsage:
    total_bytes: int
    used_bytes: int
    free_bytes: int


class ShellResult(Protocol):
    returncode: int
    stdout: str


class StorageAdb(Protocol):
    async def shell(
        self,
        serial: str,
        *args: str,
        check: bool = True,
        timeout: float | None = None,
    ) -> ShellResult: ...

    async def external_storage_roots(self, serial: str) -> list[dict[str, str]]: ...


def parse_df_storage_usage(text: str) -> StorageUsage | None:
    """Parse the data row emitted by Android/Toybox ``df -k``.

    Android variants use slightly different header labels, so parsing is based
    on the first three numeric columns after the filesystem name rather than
    on header text. Values are reported by ``df -k`` in 1024-byte blocks.
    """

    for raw in reversed(text.splitlines()):
        fields = raw.split()
        if len(fields) < 4:
            continue
        try:
            total_blocks = int(fields[1])
            used_blocks = int(fields[2])
            free_blocks = int(fields[3])
        except ValueError:
            continue
        if total_blocks <= 0 or used_blocks < 0 or free_blocks < 0:
            continue
        return StorageUsage(
            total_bytes=total_blocks * 1024,
            used_bytes=used_blocks * 1024,
            free_bytes=free_blocks * 1024,
        )
    return None


async def _filesystem_usage(adb: StorageAdb, serial: str, path: str) -> StorageUsage | None:
    result = await adb.shell(serial, "df", "-k", path, check=False, timeout=10.0)
    if result.returncode != 0:
        return None
    return parse_df_storage_usage(result.stdout)


async def collect_storage_metadata(adb: StorageAdb, serial: str) -> dict[str, str]:
    """Collect user-visible internal-storage and removable-SD capacity data."""

    metadata: dict[str, str] = {}
    internal = await _filesystem_usage(adb, serial, "/sdcard")
    if internal is not None:
        metadata.update(
            {
                "internalStorageTotalBytes": str(internal.total_bytes),
                "internalStorageUsedBytes": str(internal.used_bytes),
                "internalStorageFreeBytes": str(internal.free_bytes),
            }
        )

    roots = await adb.external_storage_roots(serial)
    metadata["sdCardPresent"] = "true" if roots else "false"
    if not roots:
        return metadata

    root = roots[0]
    path = root["path"]
    metadata["sdCardPath"] = path
    usage = await _filesystem_usage(adb, serial, path)
    if usage is not None:
        metadata.update(
            {
                "sdCardTotalBytes": str(usage.total_bytes),
                "sdCardUsedBytes": str(usage.used_bytes),
                "sdCardFreeBytes": str(usage.free_bytes),
            }
        )
    return metadata
