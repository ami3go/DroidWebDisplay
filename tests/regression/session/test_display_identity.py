from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from droid_web_display.api import create_app
from droid_web_display.config import BridgeConfig
from droid_web_display.models import (
    AndroidDevice,
    DisplayMode,
    SessionOptions,
    VirtualDisplayOptions,
)
from droid_web_display.scrcpy.artifact import ScrcpyArtifact
from droid_web_display.scrcpy.session import ScrcpySession, SessionManager
from tests.regression.session.fakes import FakeAdb


def artifact(tmp_path: Path) -> ScrcpyArtifact:
    path = tmp_path / "scrcpy-server-v4.1"
    path.write_bytes(b"verified-test-server")
    return ScrcpyArtifact(path, "4.1", "a" * 40, "b" * 64, "scrcpy-4.1")


@pytest.mark.asyncio
async def test_physical_session_has_stable_display_identity(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device", model="Test")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0)

    session = await manager.start_session(
        serial="PHONE",
        options=SessionOptions(audio=False),
        display_name="  Primary phone  ",
    )

    display = session.to_dict()["display"]
    assert display == {
        "sessionId": session.session_id,
        "kind": "physical",
        "displayId": 0,
        "name": "Primary phone",
        "application": None,
        "resolution": {"width": None, "height": None, "source": "unknown"},
        "dpi": {"value": None, "source": "unknown"},
        "createdAt": session.created_at,
        "state": "running",
    }
    assert session.to_dict()["displayMode"] == "physical"

    await manager.close()


def test_virtual_display_identity_uses_requested_then_actual_metadata() -> None:
    options = SessionOptions(
        display_mode=DisplayMode.VIRTUAL,
        virtual_display=VirtualDisplayOptions(
            width=1280,
            height=720,
            dpi=220,
            start_app="com.openai.chatgpt",
        ),
    )
    session = ScrcpySession(
        session_id="session-1",
        serial="PHONE",
        scid=1,
        local_port=27183,
        socket_name="scrcpy_00000001",
        options=options,
        display_name="ChatGPT",
    )
    session.application = "com.openai.chatgpt"

    before = session.display_metadata()
    assert before["kind"] == "virtual"
    assert before["displayId"] is None
    assert before["resolution"] == {"width": 1280, "height": 720, "source": "requested"}
    assert before["dpi"] == {"value": 220, "source": "requested"}

    SessionManager._handle_server_log_line(
        session,
        "INFO: New display: 1360x768/240 (id=17)",
    )

    after = session.display_metadata()
    assert after["displayId"] == 17
    assert after["resolution"] == {"width": 1360, "height": 768, "source": "actual"}
    assert after["dpi"] == {"value": 240, "source": "actual"}
    assert after["name"] == "ChatGPT"
    assert after["application"] == "com.openai.chatgpt"


@pytest.mark.asyncio
async def test_blank_display_name_is_rejected_before_resources_start(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0)

    with pytest.raises(ValueError, match="visible character"):
        await manager.start_session(serial="PHONE", display_name="   ")

    assert adb.forwards == []
    assert manager.list_sessions() == []
    await manager.close()


def test_session_api_exposes_named_display_identity(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device", model="Test")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0)
    config = BridgeConfig(repo_root=tmp_path, authentication_required=False)
    app = create_app(config=config, manager=manager, adb=adb)  # type: ignore[arg-type]

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/sessions",
            json={
                "serial": "PHONE",
                "audio": False,
                "displayName": "Development",
            },
        )
        assert created.status_code == 201
        body = created.json()
        assert body["display"]["name"] == "Development"
        assert body["display"]["kind"] == "physical"
        assert body["display"]["displayId"] == 0

        listed = client.get("/api/v1/sessions")
        assert listed.status_code == 200
        assert listed.json()["sessions"][0]["display"]["sessionId"] == body["sessionId"]
        assert listed.json()["sessions"][0]["display"]["name"] == "Development"

        deleted = client.delete(f"/api/v1/sessions/{body['sessionId']}")
        assert deleted.status_code == 200


def test_session_api_rejects_blank_display_name(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device", model="Test")])
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0)
    config = BridgeConfig(repo_root=tmp_path, authentication_required=False)
    app = create_app(config=config, manager=manager, adb=adb)  # type: ignore[arg-type]

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/sessions",
            json={"serial": "PHONE", "displayName": "   "},
        )
        assert response.status_code == 422
        assert "visible character" in response.json()["detail"]

    assert adb.forwards == []
