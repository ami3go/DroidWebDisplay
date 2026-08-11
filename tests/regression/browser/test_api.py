from pathlib import Path

from fastapi.testclient import TestClient

from gpt_bridge.api import create_app
from gpt_bridge.config import BridgeConfig
from gpt_bridge.models import AndroidDevice
from gpt_bridge.scrcpy.artifact import ScrcpyArtifact
from gpt_bridge.scrcpy.session import SessionManager
from tests.regression.session.fakes import FakeAdb


def test_phase4_api_and_static_client(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    fake = FakeAdb([AndroidDevice("PHONE", "device", model="SM-G980F", android_version="13", sdk=33)])
    server = root / "server" / "test-placeholder"
    artifact = ScrcpyArtifact(server, "4.1", "a" * 40, "b" * 64, "scrcpy-4.1")
    manager = SessionManager(fake, artifact)
    app = create_app(config=BridgeConfig(repo_root=root, transfer_data_directory=tmp_path / "data", default_download_directory=tmp_path / "downloads", authentication_required=False), manager=manager, adb=fake)  # type: ignore[arg-type]

    with TestClient(app) as client:
        version = client.get("/api/v1/version")
        assert version.status_code == 200
        assert version.json()["phase"] == 9
        support = client.get("/api/v1/browser-support")
        assert support.json()["videoCodec"] == "h264"
        assert support.json()["softwareDecoderFallback"] is False
        page = client.get("/")
        assert page.status_code == 200
        assert "Gpt-Bridge" in page.text
        assert "/assets/main.js" in page.text
