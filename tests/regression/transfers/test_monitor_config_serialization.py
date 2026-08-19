from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from droid_web_display.transfers.monitor import AutoDownloadConfig, AutoDownloadMonitor


class DummyAdb:
    pass


class DummyTransfers:
    def __init__(self, root: Path) -> None:
        self.root = root

    def destination_path(self, _profile_id: str) -> Path:
        return self.root


@pytest.mark.asyncio
async def test_configuration_waits_for_in_progress_scan(tmp_path: Path) -> None:
    monitor = AutoDownloadMonitor(
        DummyAdb(),  # type: ignore[arg-type]
        DummyTransfers(tmp_path / "downloads"),  # type: ignore[arg-type]
        data_directory=tmp_path / "data",
    )
    updated = AutoDownloadConfig(enabled=True, serial="PHONE", source_path="/sdcard/Documents")

    await monitor._scan_lock.acquire()
    try:
        task = asyncio.create_task(monitor.configure(updated))
        await asyncio.sleep(0)
        assert task.done() is False
        assert monitor.config.serial is None
    finally:
        monitor._scan_lock.release()

    await asyncio.wait_for(task, timeout=0.5)
    assert monitor.config.serial == "PHONE"
    assert monitor.config.source_path == "/sdcard/Documents"


@pytest.mark.asyncio
async def test_clear_history_waits_for_in_progress_scan(tmp_path: Path) -> None:
    monitor = AutoDownloadMonitor(
        DummyAdb(),  # type: ignore[arg-type]
        DummyTransfers(tmp_path / "downloads"),  # type: ignore[arg-type]
        data_directory=tmp_path / "data",
    )
    monitor._processed["remote"] = 1.0
    monitor._processed_local["local"] = 1.0

    await monitor._scan_lock.acquire()
    try:
        task = asyncio.create_task(monitor.clear_history())
        await asyncio.sleep(0)
        assert task.done() is False
        assert monitor._processed == {"remote": 1.0}
        assert monitor._processed_local == {"local": 1.0}
    finally:
        monitor._scan_lock.release()

    await asyncio.wait_for(task, timeout=0.5)
    assert monitor._processed == {}
    assert monitor._processed_local == {}
