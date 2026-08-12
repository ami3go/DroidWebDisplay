from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from droid_web_display.api import create_app
from droid_web_display.auth import AuthService
from droid_web_display.config import BridgeConfig
from droid_web_display.transfers.manager import TransferManager
from tests.security.test_api import FakeAdb, FakeSessionManager, FakeSync


def make_app(tmp_path: Path):
    adb = FakeAdb()
    transfers = TransferManager(
        adb,
        FakeSync(),
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
    )  # type: ignore[arg-type]
    config = BridgeConfig(
        repo_root=Path(__file__).resolve().parents[3],
        transfer_data_directory=tmp_path / "data",
        default_download_directory=tmp_path / "downloads",
        authentication_required=True,
        auth_data_file=tmp_path / "data" / "auth.json",
    )
    return create_app(
        config=config,
        manager=FakeSessionManager(),  # type: ignore[arg-type]
        adb=adb,  # type: ignore[arg-type]
        transfers=transfers,
        auth=AuthService(config.resolved_auth_data_file),
    )


def payload(name: str = "S20 Daily") -> dict:
    return {
        "name": name,
        "device": {"serial": "PHONE", "model": "Test Phone"},
        "display": {
            "displayMode": "virtual",
            "profileId": "low-latency",
            "sizeMode": "fixed",
            "width": 1280,
            "height": 720,
            "dpi": 220,
            "startApp": "com.openai.chatgpt",
            "forceStopBeforeLaunch": False,
            "keepActive": True,
            "systemDecorations": True,
            "destroyContentOnClose": True,
            "imePolicy": "local",
            "preserveAspectRatio": True,
            "videoBitRateMbps": 10,
            "maxFps": 60,
        },
        "audio": {"enabled": False, "muted": False, "volume": 100},
        "clipboard": {"automatic": False, "maximumKiB": 256},
        "reconnect": {"enabled": True, "attempts": 5},
        "video": {"encoderMode": "auto", "encoder": None},
    }


def test_profile_crud_is_authenticated_csrf_protected_and_persistent(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/v1/profiles").status_code == 401
        setup = client.post(
            "/api/v1/auth/setup",
            json={"pin": "123456", "confirmPin": "123456", "duration": "1-day"},
        )
        assert setup.status_code == 201
        csrf = setup.json()["csrfToken"]
        headers = {"x-droidwebdisplay-csrf": csrf}

        assert client.post("/api/v1/profiles", json=payload()).status_code == 403
        created_response = client.post("/api/v1/profiles", json=payload(), headers=headers)
        assert created_response.status_code == 201, created_response.text
        created = created_response.json()
        profile_id = created["id"]
        assert created["schemaVersion"] == 1
        assert "pin" not in created

        listing = client.get("/api/v1/profiles").json()
        assert listing["defaultProfileId"] is None
        assert [item["id"] for item in listing["profiles"]] == [profile_id]

        default = client.put(f"/api/v1/profiles/{profile_id}/default", headers=headers)
        assert default.status_code == 200
        assert default.json()["defaultProfileId"] == profile_id

        updated_payload = payload("S20 Daily Updated")
        updated = client.put(f"/api/v1/profiles/{profile_id}", json=updated_payload, headers=headers)
        assert updated.status_code == 200
        assert updated.json()["name"] == "S20 Daily Updated"

        used = client.post(f"/api/v1/profiles/{profile_id}/used", headers=headers)
        assert used.status_code == 200
        assert used.json()["lastUsedAt"]

        deleted = client.delete(f"/api/v1/profiles/{profile_id}", headers=headers)
        assert deleted.status_code == 204
        listing = client.get("/api/v1/profiles").json()
        assert listing["profiles"] == []
        assert listing["defaultProfileId"] is None

    assert (tmp_path / "data" / "connection-profiles.json").is_file()


def test_profile_api_forbids_security_fields_and_duplicate_names(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        setup = client.post(
            "/api/v1/auth/setup",
            json={"pin": "123456", "confirmPin": "123456", "duration": "1-day"},
        )
        headers = {"x-droidwebdisplay-csrf": setup.json()["csrfToken"]}
        assert client.post("/api/v1/profiles", json=payload(), headers=headers).status_code == 201
        assert client.post("/api/v1/profiles", json=payload("s20 daily"), headers=headers).status_code == 409

        unsafe = payload("Unsafe")
        unsafe["network"] = {"mode": "lan-https"}
        response = client.post("/api/v1/profiles", json=unsafe, headers=headers)
        assert response.status_code == 422
