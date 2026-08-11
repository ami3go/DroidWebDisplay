from __future__ import annotations

from pathlib import Path

import pytest

from droid_web_display.auth import AuthError, AuthService
from droid_web_display.errors import TransferConflictError, TransferValidationError
from droid_web_display.models import SessionOptions, SessionState
from droid_web_display.network_access import (
    LAN_HTTPS,
    NetworkAccessConfig,
    NetworkConfigStore,
    TlsSettings,
)
from droid_web_display.scrcpy.session import ScrcpySession, SessionManager
from droid_web_display.transfers.adb_sync import AdbSyncStat
from droid_web_display.transfers.manager import TransferManager
from droid_web_display.transfers.models import TransferDirection, TransferRecord, TransferState


class FakeAdb:
    async def get_state(self, serial: str) -> str:
        return "device"


class LargeSync:
    def __init__(self, size: int = 1024) -> None:
        self.size = size
        self.pull_calls = 0

    async def stat(self, serial: str, path: str) -> AdbSyncStat:
        return AdbSyncStat(0o100664, self.size, 1)

    async def pull(self, *args, **kwargs) -> None:
        self.pull_calls += 1


def test_initial_pin_setup_is_rejected_in_lan_mode(tmp_path: Path) -> None:
    auth = AuthService(tmp_path / "auth.json")
    with pytest.raises(AuthError, match="local PC"):
        auth.setup(
            "123456",
            duration="1-day",
            custom_seconds=None,
            user_agent="test",
            access_mode="lan",
        )
    assert auth.configured is False


def test_saved_lan_config_falls_back_to_loopback_without_auth(tmp_path: Path) -> None:
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("placeholder", encoding="utf-8")
    key.write_text("placeholder", encoding="utf-8")
    store = NetworkConfigStore(tmp_path / "network-access.json")
    store.save(
        NetworkAccessConfig(
            mode=LAN_HTTPS,
            bind_address="192.168.50.20",
            port=8765,
            allowed_networks=("192.168.50.0/24",),
            tls=TlsSettings(
                enabled=True,
                certificate_path=str(cert),
                private_key_path=str(key),
            ),
        )
    )

    recovered = store.load()
    assert recovered.mode == "local-only"
    assert recovered.bind_address == "127.0.0.1"
    assert recovered.port == 8765

    AuthService(tmp_path / "auth.json").setup(
        "123456",
        duration="1-day",
        custom_seconds=None,
        user_agent="test",
        access_mode="local",
    )
    assert store.load().mode == LAN_HTTPS


@pytest.mark.asyncio
async def test_rejected_upload_releases_owned_spool_file(tmp_path: Path) -> None:
    manager = TransferManager(
        FakeAdb(),
        LargeSync(),
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
        maximum_queue_length=1,
    )  # type: ignore[arg-type]
    spool = tmp_path / "data" / "upload-spool" / "rejected.bin.part"
    spool.parent.mkdir(parents=True)
    spool.write_bytes(b"payload")
    manager._records["busy"] = TransferRecord(
        transfer_id="busy",
        direction=TransferDirection.DOWNLOAD,
        serial="PHONE",
        source_path="/sdcard/busy.bin",
        destination_path=str(tmp_path / "downloads" / "busy.bin"),
        filename="busy.bin",
        state=TransferState.QUEUED,
    )

    with pytest.raises(TransferConflictError, match="queue is full"):
        await manager.enqueue_upload(
            serial="PHONE",
            spool_path=spool,
            original_filename="rejected.bin",
            size=spool.stat().st_size,
            destination_directory="/sdcard/Download",
        )
    assert not spool.exists()


@pytest.mark.asyncio
async def test_download_respects_configured_maximum_file_size(tmp_path: Path) -> None:
    sync = LargeSync(size=1024)
    manager = TransferManager(
        FakeAdb(),
        sync,
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
        maximum_file_size=100,
    )  # type: ignore[arg-type]
    final_path = tmp_path / "downloads" / "big.bin"
    record = TransferRecord(
        transfer_id="download",
        direction=TransferDirection.DOWNLOAD,
        serial="PHONE",
        source_path="/sdcard/big.bin",
        destination_path=str(final_path),
        filename="big.bin",
        internal_local_path=str(final_path),
    )

    with pytest.raises(TransferValidationError, match="maximum size"):
        await manager._run_download(record)
    assert sync.pull_calls == 0


@pytest.mark.asyncio
async def test_optional_audio_disconnect_does_not_stop_session() -> None:
    manager = SessionManager(FakeAdb())  # type: ignore[arg-type]
    session = ScrcpySession(
        session_id="session",
        serial="PHONE",
        scid=1,
        local_port=27183,
        socket_name="scrcpy_test",
        options=SessionOptions(audio=True),
        state=SessionState.RUNNING,
    )
    manager._sessions[session.session_id] = session

    result = await manager.stop_session(
        session.session_id,
        reason="browser_audio_browser_disconnected",
    )

    assert result is session
    assert session.state == SessionState.RUNNING
    assert session.stopped_at is None
    assert any("optional audio channel detached" in line for line in session.server_log)
