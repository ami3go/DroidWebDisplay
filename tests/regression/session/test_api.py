from pathlib import Path

from fastapi.testclient import TestClient

from droid_web_display.adb.client import AdbClient
from droid_web_display.api import create_app
from droid_web_display.config import BridgeConfig
from droid_web_display.models import AndroidDevice
from droid_web_display.scrcpy.artifact import ScrcpyArtifact
from droid_web_display.scrcpy.session import SessionManager
from tests.regression.session.fakes import FakeAdb


def test_health_and_device_api(tmp_path: Path) -> None:
    fake = FakeAdb(
        [
            AndroidDevice(
                "PHONE",
                "device",
                model="Pixel",
                manufacturer="Google",
                android_version="16",
                sdk=36,
                connection_type="usb",
            )
        ]
    )
    server = tmp_path / "server"
    server.write_bytes(b"server")
    artifact = ScrcpyArtifact(server, "4.1", "a" * 40, "b" * 64, "scrcpy-4.1")
    manager = SessionManager(fake, artifact)
    config = BridgeConfig(repo_root=tmp_path, authentication_required=False)
    app = create_app(config=config, manager=manager, adb=fake)  # type: ignore[arg-type]

    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["phase"] == 9
        devices = client.get("/api/v1/devices")
        assert devices.status_code == 200
        assert devices.json()["devices"][0]["serial"] == "PHONE"
        diagnostics = client.get("/api/v1/diagnostics")
        assert diagnostics.json()["bridgeStreamRole"] == "opaque-binary-proxy"


def test_api_creation_is_lazy_when_server_artifact_is_missing(tmp_path: Path) -> None:
    config = BridgeConfig(repo_root=tmp_path, authentication_required=False)
    app = create_app(config=config, adb=AdbClient("missing-adb-for-test"))
    assert app.title == "DroidWebDisplay Local Service"
