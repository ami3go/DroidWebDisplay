from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from droid_web_display.api.app import create_app
from droid_web_display.auth import AuthService
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


def make_app(tmp_path: Path):
    adb = FakeAdb()
    transfers = TransferManager(
        adb,
        FakeSync(),
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
    )  # type: ignore[arg-type]
    config = BridgeConfig(
        repo_root=Path(__file__).resolve().parents[2],
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


def setup_client(client: TestClient, *, duration: str = "1-day") -> dict:
    response = client.post("/api/v1/auth/setup", json={
        "pin": "123456",
        "confirmPin": "123456",
        "duration": duration,
        "label": "Gate 8 browser",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_untrusted_api_and_websocket_are_rejected_then_cookie_auth_works(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/v1/devices").status_code == 401
        with pytest.raises(WebSocketDisconnect) as denied:
            with client.websocket_connect("/ws/v1/events") as websocket:
                websocket.receive_json()
        assert denied.value.code == 4401

        status = setup_client(client)
        cookie = client.cookies.get("droid_web_display_id")
        assert cookie
        set_cookie = client.post  # retain client reference for type checkers
        del set_cookie
        assert status["authenticated"] is True
        assert status["phoneAuthoritative"] is False
        assert status["trustModel"] == "pc-local"
        assert client.get("/api/v1/devices").status_code == 200
        with client.websocket_connect("/ws/v1/events") as websocket:
            assert websocket.receive_json()["phase"] == 9


def test_cookie_flags_csrf_custom_duration_and_revocation(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    with TestClient(app) as client:
        setup_response = client.post("/api/v1/auth/setup", json={
            "pin": "123456",
            "confirmPin": "123456",
            "duration": "1-day",
        })
        assert setup_response.status_code == 201
        cookie_header = setup_response.headers["set-cookie"].lower()
        assert "httponly" in cookie_header
        assert "samesite=strict" in cookie_header
        assert "123456" not in setup_response.text
        csrf = setup_response.json()["csrfToken"]

        assert client.post("/api/v1/auto-download/reset").status_code == 403
        assert client.post("/api/v1/auto-download/reset", headers={"x-droidwebdisplay-csrf": csrf}).status_code == 200
        assert client.post(
            "/api/v1/auto-download/reset",
            headers={"x-droidwebdisplay-csrf": csrf, "origin": "http://evil.example"},
        ).status_code == 403

        invalid_custom = client.post("/api/v1/auth/login", json={
            "pin": "123456",
            "duration": "custom",
            "customSeconds": 299,
        })
        assert invalid_custom.status_code == 422
        second = client.post("/api/v1/auth/login", json={
            "pin": "123456",
            "duration": "custom",
            "customSeconds": 600,
            "label": "Second browser",
        })
        assert second.status_code == 200
        csrf = second.json()["csrfToken"]
        sessions = client.get("/api/v1/auth/sessions").json()["sessions"]
        assert len(sessions) == 2
        old = next(item for item in sessions if not item["current"])
        revoked = client.delete(
            f"/api/v1/auth/sessions/{old['sessionId']}",
            headers={"x-droidwebdisplay-csrf": csrf},
        )
        assert revoked.json()["revoked"] is True

        global_result = client.post(
            "/api/v1/auth/sessions/revoke-all",
            json={"pin": "123456"},
            headers={"x-droidwebdisplay-csrf": csrf},
        )
        assert global_result.status_code == 200
        assert global_result.json()["revoked"] >= 1
        assert client.get("/api/v1/devices").status_code == 401

        audit_text = (tmp_path / "data" / "auth.json").read_text(encoding="utf-8").lower()
        assert "123456" not in audit_text
        assert client.cookies.get("droid_web_display_id") is None


def test_openapi_declares_pc_local_cookie_security(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    schema = app.openapi()
    scheme = schema["components"]["securitySchemes"]["pcLocalSession"]
    assert scheme["type"] == "apiKey"
    assert scheme["in"] == "cookie"
    assert scheme["name"] == "droid_web_display_id"
    assert schema["paths"]["/api/v1/devices"]["get"]["security"] == [{"pcLocalSession": []}]
    assert "security" not in schema["paths"]["/api/v1/auth/login"]["post"]
    assert schema["info"]["x-trust-model"].startswith("PC-local")
