from __future__ import annotations

from pathlib import Path

from droid_web_display.transfers.manager import TransferManager
from droid_web_display.transfers.models import TransferDirection, TransferRecord, TransferState


class DummyAdb:
    pass


class DummySync:
    pass


def make_record(index: int, state: TransferState) -> TransferRecord:
    return TransferRecord(
        transfer_id=f"transfer-{index}",
        direction=TransferDirection.DOWNLOAD,
        serial="PHONE",
        source_path=f"/sdcard/Download/{index}.bin",
        destination_path=f"/tmp/{index}.bin",
        filename=f"{index}.bin",
        state=state,
        created_at=float(index),
    )


def test_transfer_history_keeps_active_and_latest_500_final_records(tmp_path: Path) -> None:
    manager = TransferManager(
        DummyAdb(),  # type: ignore[arg-type]
        DummySync(),  # type: ignore[arg-type]
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
    )
    for index in range(525):
        record = make_record(index, TransferState.COMPLETED)
        manager._records[record.transfer_id] = record
    active = make_record(-1, TransferState.TRANSFERRING)
    manager._records[active.transfer_id] = active

    records = manager.list_records()

    finals = [record for record in records if record.state == TransferState.COMPLETED]
    assert len(finals) == 500
    assert active in records
    assert "transfer-0" not in manager._records
    assert "transfer-24" not in manager._records
    assert "transfer-25" in manager._records
    assert "transfer-524" in manager._records
    assert len(manager._records) == 501
