from pathlib import Path

from fastapi.testclient import TestClient

from droid_web_display.api import create_app
from droid_web_display.config import BridgeConfig
from droid_web_display.models import AndroidDevice
from droid_web_display.scrcpy.artifact import ScrcpyArtifact
from droid_web_display.scrcpy.session import SessionManager
from tests.regression.session.fakes import FakeAdb


def artifact(tmp_path: Path) -> ScrcpyArtifact:
    path = tmp_path / "scrcpy-server-v4.1"
    path.write_bytes(b"verified-test-server")
    return ScrcpyArtifact(path, "4.1", "a" * 40, "b" * 64, "scrcpy-4.1")


def make_client(tmp_path: Path, devices: list[AndroidDevice]):
    adb = FakeAdb(devices)
    manager = SessionManager(adb, artifact(tmp_path), connect_timeout=2.0, monitor_interval=10)
    config = BridgeConfig(repo_root=tmp_path, authentication_required=False)
    app = create_app(config=config, manager=manager, adb=adb)  # type: ignore[arg-type]
    return TestClient(app), manager, adb


def test_device_scoped_api_creates_lists_and_stops_independent_sessions(tmp_path: Path) -> None:
    client, manager, adb = make_client(tmp_path, [AndroidDevice("PHONE", "device", model="Test")])
    with client:
        first = client.post(
            "/api/v1/devices/PHONE/sessions",
            json={"audio": False, "displayName": "Phone"},
        )
        second = client.post(
            "/api/v1/devices/PHONE/sessions",
            json={"audio": False, "displayName": "Development"},
        )
        assert first.status_code == 201
        assert second.status_code == 201
        first_body = first.json()
        second_body = second.json()
        assert first_body["sessionId"] != second_body["sessionId"]
        assert first_body["serial"] == second_body["serial"] == "PHONE"

        listed = client.get("/api/v1/devices/PHONE/sessions")
        assert listed.status_code == 200
        payload = listed.json()
        assert payload["serial"] == "PHONE"
        assert payload["activeSessionCount"] == 2
        assert payload["maximumSessions"] == 4
        assert payload["availableSlots"] == 2
        assert [item["display"]["name"] for item in payload["sessions"]] == ["Phone", "Development"]

        stopped = client.delete(f"/api/v1/devices/PHONE/sessions/{first_body['sessionId']}")
        assert stopped.status_code == 200
        assert stopped.json()["state"] == "stopped"
        remaining = client.get("/api/v1/devices/PHONE/sessions").json()
        assert remaining["activeSessionCount"] == 1
        assert remaining["sessions"][0]["sessionId"] == second_body["sessionId"]
        assert second_body["localPort"] in adb.forward_servers

        bulk = client.delete("/api/v1/devices/PHONE/sessions")
        assert bulk.status_code == 200
        assert bulk.json()["stoppedCount"] == 1
        assert bulk.json()["sessions"][0]["sessionId"] == second_body["sessionId"]
        assert client.get("/api/v1/devices/PHONE/sessions").json()["activeSessionCount"] == 0
        assert not manager.list_sessions_for_device("PHONE")


def test_device_scoped_create_rejects_conflicting_body_serial(tmp_path: Path) -> None:
    client, manager, _ = make_client(
        tmp_path,
        [AndroidDevice("PHONE", "device"), AndroidDevice("OTHER", "device")],
    )
    with client:
        response = client.post(
            "/api/v1/devices/PHONE/sessions",
            json={"serial": "OTHER", "audio": False},
        )
        assert response.status_code == 422
        assert "must match" in response.json()["detail"]
        assert manager.list_sessions_for_device("PHONE") == []
        assert manager.list_sessions_for_device("OTHER") == []


def test_device_scoped_delete_cannot_stop_other_device_session(tmp_path: Path) -> None:
    client, manager, _ = make_client(
        tmp_path,
        [AndroidDevice("PHONE", "device"), AndroidDevice("OTHER", "device")],
    )
    with client:
        created = client.post(
            "/api/v1/devices/OTHER/sessions",
            json={"audio": False, "displayName": "Other phone"},
        )
        assert created.status_code == 201
        session_id = created.json()["sessionId"]

        wrong_device = client.delete(f"/api/v1/devices/PHONE/sessions/{session_id}")
        assert wrong_device.status_code == 404
        assert manager.get_session(session_id).state.value == "running"

        correct_device = client.delete(f"/api/v1/devices/OTHER/sessions/{session_id}")
        assert correct_device.status_code == 200
        assert correct_device.json()["state"] == "stopped"


def test_device_scoped_list_rejects_unknown_device(tmp_path: Path) -> None:
    client, _, _ = make_client(tmp_path, [AndroidDevice("PHONE", "device")])
    with client:
        response = client.get("/api/v1/devices/MISSING/sessions")
        assert response.status_code == 404


def test_device_session_limit_returns_409_and_diagnostics_report_capacity(tmp_path: Path) -> None:
    adb = FakeAdb([AndroidDevice("PHONE", "device", model="Test")])
    manager = SessionManager(
        adb,
        artifact(tmp_path),
        connect_timeout=2.0,
        monitor_interval=10,
        maximum_sessions_per_device=2,
    )
    config = BridgeConfig(repo_root=tmp_path, authentication_required=False, maximum_display_sessions=2)
    app = create_app(config=config, manager=manager, adb=adb)  # type: ignore[arg-type]
    with TestClient(app) as client:
        first = client.post("/api/v1/devices/PHONE/sessions", json={"audio": False, "displayName": "Phone"})
        second = client.post("/api/v1/devices/PHONE/sessions", json={"audio": False, "displayName": "Work"})
        assert first.status_code == second.status_code == 201

        rejected = client.post("/api/v1/devices/PHONE/sessions", json={"audio": False, "displayName": "Overflow"})
        assert rejected.status_code == 409
        error = rejected.json()["error"]
        assert error["code"] == "session_conflict"
        assert error["details"]["maximumSessions"] == 2
        assert error["details"]["availableSlots"] == 0

        diagnostics = client.get("/api/v1/devices/PHONE/display-diagnostics")
        assert diagnostics.status_code == 200
        payload = diagnostics.json()
        assert payload["capacity"]["activeSessions"] == 2
        assert payload["capacity"]["maximumSessions"] == 2
        assert payload["capacity"]["availableSlots"] == 0
        assert {item["display"]["name"] for item in payload["displays"]} == {"Phone", "Work"}
        assert all("channelDiagnostics" in item for item in payload["displays"])
