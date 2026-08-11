from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from droid_web_display.adb.running_apps import RunningGuiApp, parse_running_gui_apps, validate_component_name
from droid_web_display.api.app import create_app
from droid_web_display.config import BridgeConfig
from droid_web_display.models import AndroidDevice, DisplayMode, SessionOptions, SessionState, VirtualDisplayOptions
from droid_web_display.scrcpy.artifact import ScrcpyArtifact
from droid_web_display.scrcpy.session import ScrcpySession, SessionManager
from tests.regression.virtual_display.test_api import VirtualDisplayFakeAdb


DUMPSYS = """
Display #0 (activities from top to bottom):
  * Task{aaa #42 type=standard A=10123:com.example.notes U=0 visible=true visibleRequested=true mode=fullscreen}
    topResumedActivity=ActivityRecord{bbb u0 com.example.notes/.MainActivity t42}
  * Task{ccc #55 type=standard A=10124:com.openai.chatgpt U=0 visible=false mode=fullscreen}
    * Hist #0: ActivityRecord{ddd u0 com.openai.chatgpt/com.openai.chatgpt.MainActivity t55}
Display #299 (activities from top to bottom):
  * Task{eee #77 type=standard A=10125:org.mozilla.firefox U=0 visible=true mode=fullscreen}
    mResumedActivity: ActivityRecord{fff u0 org.mozilla.firefox/.App t77}
"""


def test_parse_running_gui_apps_tracks_task_display_and_visibility() -> None:
    apps = parse_running_gui_apps(DUMPSYS)
    by_task = {item.task_id: item for item in apps}
    assert set(by_task) == {42, 55, 77}
    assert by_task[42].component_name == "com.example.notes/.MainActivity"
    assert by_task[42].display_id == 0
    assert by_task[42].visible is True
    assert by_task[42].resumed is True
    assert by_task[77].display_id == 299
    assert by_task[55].label == "ChatGPT"


def test_component_validation_rejects_shell_fragments() -> None:
    assert validate_component_name("com.example.app/.MainActivity") == "com.example.app/.MainActivity"
    for value in ("com.example.app/.Main;rm", "com example/.Main", "com.example", "'com.example/.Main'"):
        try:
            validate_component_name(value)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsafe component accepted: {value}")


class RunningAppsFakeAdb(VirtualDisplayFakeAdb):
    def __init__(self, devices: list[AndroidDevice]) -> None:
        super().__init__(devices)
        self.apps = [
            RunningGuiApp(42, "com.example.notes", "com.example.notes/.MainActivity", 0, True, True, "Notes")
        ]
        self.moves: list[tuple[str, int, str, int]] = []

    async def list_running_gui_apps(self, serial: str) -> list[RunningGuiApp]:
        return list(self.apps)

    async def move_running_app_to_display(
        self, serial: str, *, task_id: int, component_name: str, display_id: int
    ) -> dict[str, object]:
        self.moves.append((serial, task_id, component_name, display_id))
        self.apps = [RunningGuiApp(task_id, "com.example.notes", component_name, display_id, True, True, "Notes")]
        return {
            "strategy": "start-activity-on-display",
            "taskId": task_id,
            "componentName": component_name,
            "displayId": display_id,
            "output": "Starting: Intent",
        }


def test_running_apps_api_moves_validated_task_to_active_virtual_display(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    adb = RunningAppsFakeAdb([AndroidDevice("PHONE", "device", model="SM-G980F", sdk=33)])
    artifact = ScrcpyArtifact(root / "server" / "test-placeholder", "4.1", "a" * 40, "b" * 64, "scrcpy-4.1")
    manager = SessionManager(adb, artifact)
    options = SessionOptions(
        display_mode=DisplayMode.VIRTUAL,
        virtual_display=VirtualDisplayOptions(start_app="com.openai.chatgpt"),
    )
    session = ScrcpySession("SESSION", "PHONE", 0x12345678, 55123, "scrcpy_12345678", options)
    session.state = SessionState.RUNNING
    session.display_id = 299
    manager._sessions[session.session_id] = session  # test fixture owns the manager

    app = create_app(
        config=BridgeConfig(
            repo_root=root,
            transfer_data_directory=tmp_path / "data",
            default_download_directory=tmp_path / "downloads",
            authentication_required=False,
        ),
        manager=manager,
        adb=adb,  # type: ignore[arg-type]
    )
    with TestClient(app) as client:
        listed = client.get("/api/v1/devices/PHONE/running-apps")
        assert listed.status_code == 200
        assert listed.json()["apps"][0]["taskId"] == 42

        moved = client.post(
            "/api/v1/sessions/SESSION/virtual-display/move-running-app",
            json={"taskId": 42, "componentName": "com.example.notes/.MainActivity"},
        )
        assert moved.status_code == 200
        assert moved.json()["verified"] is True
        assert moved.json()["displayId"] == 299
        assert adb.moves == [("PHONE", 42, "com.example.notes/.MainActivity", 299)]
