from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from droid_web_display.api.app import create_app
from droid_web_display.config import BridgeConfig
from droid_web_display.models import AndroidDevice
from droid_web_display.scrcpy.artifact import ScrcpyArtifact
from droid_web_display.scrcpy.session import SessionManager
from tests.regression.session.fakes import FakeAdb


class VirtualDisplayFakeAdb(FakeAdb):
    async def package_installed(self, serial: str, package_name: str) -> bool:
        return package_name == "com.openai.chatgpt"

    async def supported_video_codecs(self, serial: str) -> list[str]:
        return ["h264", "h265"]

    async def list_launchable_apps(self, serial: str) -> list[dict[str, str]]:
        return [{"label": "ChatGPT", "packageName": "com.openai.chatgpt"}]


def test_phase6_capability_apps_profiles_and_validation(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    adb = VirtualDisplayFakeAdb([AndroidDevice("PHONE", "device", model="SM-G980F", manufacturer="samsung", android_version="13", sdk=33)])
    artifact = ScrcpyArtifact(root / "server" / "test-placeholder", "4.1", "a" * 40, "b" * 64, "scrcpy-4.1")
    manager = SessionManager(adb, artifact)
    app = create_app(
        config=BridgeConfig(repo_root=root, transfer_data_directory=tmp_path / "data", default_download_directory=tmp_path / "downloads", authentication_required=False),
        manager=manager,
        adb=adb,  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        capabilities = client.get("/api/v1/devices/PHONE/virtual-display-capabilities")
        assert capabilities.status_code == 200
        assert capabilities.json()["virtualDisplaySupported"] is True
        assert capabilities.json()["supportedCodecs"] == ["h264", "h265"]
        assert capabilities.json()["localImePolicySupported"] is False
        assert capabilities.json()["warnings"]
        apps = client.get("/api/v1/devices/PHONE/apps")
        assert apps.json()["apps"][0]["packageName"] == "com.openai.chatgpt"
        profiles = client.get("/api/v1/virtual-display-profiles")
        assert any(value["profileId"] == "chatgpt-desktop" for value in profiles.json()["profiles"])
        invalid = client.post("/api/v1/sessions", json={
            "serial": "PHONE",
            "displayMode": "virtual",
            "virtualDisplay": {"width": 320, "height": 900, "dpi": 240},
        })
        assert invalid.status_code == 422
        missing = client.post("/api/v1/sessions", json={
            "serial": "PHONE",
            "displayMode": "virtual",
            "virtualDisplay": {
                "width": 1600,
                "height": 900,
                "dpi": 240,
                "startApp": "com.example.missing",
            },
        })
        assert missing.status_code == 422
