from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from droid_web_display.api.app import create_app
from droid_web_display.config import BridgeConfig
from droid_web_display.models import AndroidDevice
from droid_web_display.transfers.adb_sync import AdbSyncEntry, AdbSyncStat
from droid_web_display.transfers.manager import TransferManager


class FakeAdb:
    async def version(self):
        return "Android Debug Bridge version test"

    async def get_state(self, serial: str):
        return "device"

    async def mkdir(self, serial: str, remote_directory: str):
        return None


class FakeSessionManager:
    async def close(self):
        return None

    async def list_devices(self, *, enrich=False):
        return [AndroidDevice("PHONE", "device", model="Test Phone")]

    def list_sessions(self):
        return []


class FakeSync:
    def __init__(self):
        self.remote = {"/sdcard/Download/result.txt": b"result"}

    async def list(self, serial, path):
        return [AdbSyncEntry("result.txt", 0o100664, 6, 1)]

    async def stat(self, serial, path):
        data = self.remote.get(path)
        return AdbSyncStat(0 if data is None else 0o100664, 0 if data is None else len(data), 1)

    async def push(self, serial, local_path, remote_path, *, progress=None, mode=0o100664):
        data = local_path.read_bytes()
        self.remote[remote_path] = data
        if progress:
            await progress(len(data), len(data))
        return len(data)

    async def pull(self, serial, remote_path, local_path, *, progress=None):
        data = self.remote[remote_path]
        local_path.write_bytes(data)
        if progress:
            await progress(len(data), len(data))
        return len(data)


def wait_completed(client: TestClient, transfer_id: str) -> dict:
    for _ in range(100):
        payload = client.get(f"/api/v1/transfers/{transfer_id}").json()
        if payload["state"] in {"completed", "failed", "cancelled"}:
            return payload
        time.sleep(0.01)
    raise AssertionError("transfer did not complete")


def test_phase5_storage_and_transfer_endpoints(tmp_path: Path) -> None:
    adb = FakeAdb()
    transfers = TransferManager(adb, FakeSync(), data_directory=tmp_path / "data", destination_profiles={"default-downloads": tmp_path / "downloads"})  # type: ignore[arg-type]
    app = create_app(
        config=BridgeConfig(repo_root=Path(__file__).resolve().parents[3], transfer_data_directory=tmp_path / "data", default_download_directory=tmp_path / "downloads", authentication_required=False),
        manager=FakeSessionManager(),  # type: ignore[arg-type]
        adb=adb,  # type: ignore[arg-type]
        transfers=transfers,
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/version").json()["phase"] == 9
        storage = client.get("/api/v1/storage/android", params={"serial": "PHONE", "path": "/sdcard/Download"})
        assert storage.status_code == 200
        assert storage.json()["entries"][0]["name"] == "result.txt"
        profiles = client.get("/api/v1/destination-profiles").json()
        assert profiles["profiles"][0]["id"] == "default-downloads"

        upload = client.post(
            "/api/v1/transfers/upload",
            data={"serial": "PHONE", "destinationPath": "/sdcard/Download", "duplicatePolicy": "rename"},
            files={"file": ("upload.txt", b"uploaded", "text/plain")},
        )
        assert upload.status_code == 202
        assert wait_completed(client, upload.json()["transferId"])["verification"] == "size-match"

        download = client.post(
            "/api/v1/transfers/download",
            json={"serial": "PHONE", "sourcePath": "/sdcard/Download/result.txt", "destinationProfile": "default-downloads", "duplicatePolicy": "rename"},
        )
        assert download.status_code == 202
        completed = wait_completed(client, download.json()["transferId"])
        assert completed["state"] == "completed"
        assert (tmp_path / "downloads" / "result.txt").read_bytes() == b"result"

        diagnostics = client.get("/api/v1/diagnostics").json()
        assert diagnostics["transferEngine"] == "direct-adb-sync-v1"
        assert diagnostics["transferConsoleParsing"] is False
