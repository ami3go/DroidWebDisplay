from __future__ import annotations

from dataclasses import dataclass

from droid_web_display.adb.storage_metrics import collect_storage_metadata, parse_df_storage_usage


DF_INTERNAL = """Filesystem     1K-blocks     Used Available Use% Mounted on
/dev/fuse        120000000 72000000  48000000  60% /storage/emulated
"""

DF_SD_CARD = """Filesystem        1K-blocks      Used Available Use% Mounted on
/dev/block/vold/public:179,65  64000000 16000000  48000000  25% /storage/1234-ABCD
"""


@dataclass
class FakeResult:
    returncode: int
    stdout: str


class FakeStorageAdb:
    def __init__(self, *, sd_card: bool = True) -> None:
        self.sd_card = sd_card
        self.queries: list[str] = []

    async def shell(self, serial: str, *args: str, check: bool = True, timeout: float | None = None) -> FakeResult:
        assert serial == "PHONE"
        assert args[:2] == ("df", "-k")
        path = args[2]
        self.queries.append(path)
        if path == "/sdcard":
            return FakeResult(0, DF_INTERNAL)
        if path == "/storage/1234-ABCD" and self.sd_card:
            return FakeResult(0, DF_SD_CARD)
        return FakeResult(1, "")

    async def external_storage_roots(self, serial: str) -> list[dict[str, str]]:
        assert serial == "PHONE"
        if not self.sd_card:
            return []
        return [{"id": "sd-card-1234-abcd", "label": "SD card · 1234-ABCD", "path": "/storage/1234-ABCD"}]


def test_parse_df_storage_usage_converts_kib_blocks_to_bytes() -> None:
    usage = parse_df_storage_usage(DF_INTERNAL)
    assert usage is not None
    assert usage.total_bytes == 120_000_000 * 1024
    assert usage.used_bytes == 72_000_000 * 1024
    assert usage.free_bytes == 48_000_000 * 1024


async def test_collect_storage_metadata_reports_internal_and_removable_storage() -> None:
    adb = FakeStorageAdb()
    metadata = await collect_storage_metadata(adb, "PHONE")

    assert metadata["internalStorageFreeBytes"] == str(48_000_000 * 1024)
    assert metadata["internalStorageTotalBytes"] == str(120_000_000 * 1024)
    assert metadata["sdCardPresent"] == "true"
    assert metadata["sdCardPath"] == "/storage/1234-ABCD"
    assert metadata["sdCardFreeBytes"] == str(48_000_000 * 1024)
    assert metadata["sdCardTotalBytes"] == str(64_000_000 * 1024)
    assert adb.queries == ["/sdcard", "/storage/1234-ABCD"]


async def test_collect_storage_metadata_marks_missing_sd_card_without_failing() -> None:
    adb = FakeStorageAdb(sd_card=False)
    metadata = await collect_storage_metadata(adb, "PHONE")

    assert metadata["sdCardPresent"] == "false"
    assert "sdCardFreeBytes" not in metadata
    assert adb.queries == ["/sdcard"]


async def test_collect_storage_metadata_reuses_recent_probe() -> None:
    adb = FakeStorageAdb()
    first = await collect_storage_metadata(adb, "PHONE")
    second = await collect_storage_metadata(adb, "PHONE")

    assert first == second
    assert first is not second
    assert adb.queries == ["/sdcard", "/storage/1234-ABCD"]
