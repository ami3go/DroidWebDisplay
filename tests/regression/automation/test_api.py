from __future__ import annotations

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

    async def remove_file(self, serial: str, remote_path: str):
        return None

    async def external_storage_roots(self, serial: str):
        return [{"id": "sd-card-abcd-1234", "label": "SD card · ABCD-1234", "path": "/storage/ABCD-1234"}]


class FakeSessionManager:
    async def close(self):
        return None

    async def list_devices(self, *, enrich=False):
        return [AndroidDevice("PHONE", "device", model="Test Phone")]

    def list_sessions(self):
        return []


class FakeSync:
    async def list(self, serial, path):
        return [AdbSyncEntry("existing.txt", 0o100664, 8, 1)]

    async def stat(self, serial, path):
        return AdbSyncStat(0, 0, 0)


def test_phase7_roots_and_monitor_configuration(tmp_path: Path) -> None:
    adb = FakeAdb()
    transfers = TransferManager(
        adb,
        FakeSync(),
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
    )  # type: ignore[arg-type]
    app = create_app(
        config=BridgeConfig(
            repo_root=Path(__file__).resolve().parents[3],
            transfer_data_directory=tmp_path / "data",
            default_download_directory=tmp_path / "downloads",
            authentication_required=False,
        ),
        manager=FakeSessionManager(),  # type: ignore[arg-type]
        adb=adb,  # type: ignore[arg-type]
        transfers=transfers,
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/version").json()["phase"] == 9
        roots = client.get("/api/v1/storage/android-roots")
        assert roots.status_code == 200
        assert roots.json()["roots"][0]["label"] == "Internal storage · Download"
        assert {item["path"] for item in roots.json()["roots"]} >= {"/sdcard/Documents", "/storage/ABCD-1234"}

        initial = client.get("/api/v1/auto-download").json()
        assert initial["config"]["enabled"] is False
        assert initial["config"]["pcToAndroidEnabled"] is False
        assert initial["config"]["uploadDuplicatePolicy"] == "overwrite"
        configured = client.put("/api/v1/auto-download", json={
            "enabled": False,
            "pcToAndroidEnabled": True,
            "serial": "PHONE",
            "sourcePath": "/storage/emulated/0/Download",
            "destinationProfile": "default-downloads",
            "duplicatePolicy": "rename",
            "uploadDuplicatePolicy": "overwrite",
            "scanIntervalSeconds": 2,
            "stabilitySeconds": 3,
            "stabilityObservations": 3,
            "includeExisting": False,
            "includeExistingPc": False,
            "deleteAfterVerified": False,
        })
        assert configured.status_code == 200
        assert configured.json()["config"]["sourcePath"] == "/sdcard/Download"
        assert configured.json()["config"]["pcToAndroidEnabled"] is True
        scan = client.post("/api/v1/auto-download/scan")
        assert scan.status_code == 200
        assert scan.json()["runtime"]["baselineInitialized"] is True
        diagnostics = client.get("/api/v1/diagnostics").json()
        assert diagnostics["phase"] == 9
        assert diagnostics["autoDownload"]["config"]["sourcePath"] == "/sdcard/Download"
