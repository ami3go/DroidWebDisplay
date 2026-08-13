from pathlib import Path

import pytest

from droid_web_display.config import BridgeConfig


def test_phase5_session_capacity_defaults_and_validation(tmp_path: Path) -> None:
    config = BridgeConfig(repo_root=tmp_path)
    assert config.maximum_display_sessions == 4
    config.validate()
    for value in (1, 8):
        BridgeConfig(repo_root=tmp_path, maximum_display_sessions=value).validate()
    for value in (0, 9):
        with pytest.raises(ValueError, match="maximum_display_sessions"):
            BridgeConfig(repo_root=tmp_path, maximum_display_sessions=value).validate()


def test_phase5_backend_contract_is_present() -> None:
    root = Path(__file__).resolve().parents[2]
    session = (root / "droid_web_display/scrcpy/session.py").read_text(encoding="utf-8")
    api = (root / "droid_web_display/api/app.py").read_text(encoding="utf-8")
    assert "maximum_sessions_per_device: int = 4" in session
    assert "Display session limit reached for device" in session
    assert "def session_capacity" in session
    assert "/api/v1/devices/{serial}/display-diagnostics" in api
    assert '"maximumSessions"' in api
    assert '"availableSlots"' in api


def test_phase5_tab_switch_contract_is_browser_only_and_50ms_target() -> None:
    root = Path(__file__).resolve().parents[2]
    controller = (root / "apps/web-client/src/controller.ts").read_text(encoding="utf-8")
    running_apps = (root / "apps/web-client/src/running-app-controller.ts").read_text(encoding="utf-8")
    assert "const TAB_SWITCH_TARGET_MS = 50" in controller
    start = controller.index("private activateRuntime")
    end = controller.index("private bindControlDebug", start)
    switch_body = controller[start:end]
    assert "await " not in switch_body
    assert "#api" not in switch_body
    assert "startDeviceSession" not in switch_body
    assert "recordApplicationLaunch" not in switch_body
    event_start = running_apps.index('globalThis.addEventListener("droidwebdisplay-active-session"')
    event_end = running_apps.index("  }", event_start) + 3
    event_body = running_apps[event_start:event_end]
    assert "refresh(" not in event_body
    assert "#api" not in event_body


def test_phase5_browser_exposes_capacity_and_per_display_diagnostics() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "apps/web-client/static/index.html").read_text(encoding="utf-8")
    controller = (root / "apps/web-client/src/controller.ts").read_text(encoding="utf-8")
    assert 'id="display-tab-capacity"' in html
    assert 'id="display-diagnostics"' in html
    assert "renderDisplayDiagnostics" in controller
    assert "Last tab switch" in controller


def test_phase5_limit_is_exposed_by_service_launcher() -> None:
    root = Path(__file__).resolve().parents[2]
    runner = (root / "tools/run_bridge_service.py").read_text(encoding="utf-8")
    assert '"--maximum-display-sessions"' in runner
    assert "maximum_display_sessions=args.maximum_display_sessions" in runner
    assert "choices=range(1, 9)" in runner


def test_phase5_failure_cleanup_and_reconnect_are_session_scoped() -> None:
    root = Path(__file__).resolve().parents[2]
    controller = (root / "apps/web-client/src/controller.ts").read_text(encoding="utf-8")
    start = controller.index("private async handleRuntimeFailure")
    end = controller.index("private setConnectedControls", start)
    lifecycle = controller[start:end]
    assert "cleanupRuntime(sessionId)" in lifecycle
    assert "stopDeviceSessions" not in lifecycle
    assert "this.#runtimes.delete(sessionId)" in lifecycle
    reconnect_start = controller.index("private async reconnectNow")
    reconnect_end = controller.index("private browserSettings", reconnect_start)
    reconnect = controller[reconnect_start:reconnect_end]
    assert "cleanupSession()" in reconnect
    assert "stopDeviceSessions" not in reconnect