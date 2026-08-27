from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from droid_web_display.transfers.monitor import AutoDownloadConfig, AutoDownloadMonitor


class BlockingTransfers:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.scan_entered = asyncio.Event()
        self.release_scan = asyncio.Event()
        self.list_calls: list[tuple[str, str]] = []

    def destination_path(self, profile: str) -> Path:
        assert profile == "default-downloads"
        return self.root / "downloads"

    async def list_android(self, serial: str, path: str):
        self.list_calls.append((serial, path))
        self.scan_entered.set()
        await self.release_scan.wait()
        return []

    def get(self, transfer_id: str):  # pragma: no cover - no transfers in this regression
        raise AssertionError(f"unexpected transfer lookup: {transfer_id}")


@pytest.mark.asyncio
async def test_reconfigure_waits_for_in_flight_scan_before_switching_device(tmp_path: Path) -> None:
    transfers = BlockingTransfers(tmp_path)
    monitor = AutoDownloadMonitor(object(), transfers, data_directory=tmp_path / "data")  # type: ignore[arg-type]
    await monitor.configure(
        AutoDownloadConfig(enabled=True, serial="PHONE_A", source_path="/sdcard/Download")
    )

    scan = asyncio.create_task(monitor.scan_now())
    await asyncio.wait_for(transfers.scan_entered.wait(), timeout=1)

    reconfigure = asyncio.create_task(
        monitor.configure(
            AutoDownloadConfig(enabled=True, serial="PHONE_B", source_path="/sdcard/Download/NewDownload")
        )
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert not reconfigure.done(), "configuration became visible while the previous scan still held the scan lock"
    assert monitor.config.serial == "PHONE_A"
    assert monitor.config.source_path == "/sdcard/Download"

    transfers.release_scan.set()
    await asyncio.wait_for(scan, timeout=1)
    snapshot = await asyncio.wait_for(reconfigure, timeout=1)

    assert transfers.list_calls == [("PHONE_A", "/sdcard/Download")]
    assert snapshot["config"]["serial"] == "PHONE_B"
    assert snapshot["config"]["sourcePath"] == "/sdcard/Download/NewDownload"
    assert monitor.config.serial == "PHONE_B"
