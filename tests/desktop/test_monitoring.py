from __future__ import annotations

import json
from pathlib import Path

from droid_web_display.desktop import monitoring
from droid_web_display.models import AndroidDevice


def test_timeline_humanizes_server_browser_and_transfer_events(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    logs.mkdir()
    records = [
        {
            "timestamp": "2026-08-14T19:00:00.000Z",
            "event": "logging.configured",
            "message": "Server diagnostic logging configured",
        },
        {
            "timestamp": "2026-08-14T19:00:01.000Z",
            "event": "websocket.connect",
            "message": "WebSocket connect /ws",
            "client": "192.168.1.32",
            "request_id": "one",
        },
        {
            "timestamp": "2026-08-14T19:00:02.000Z",
            "event": "transfer.failed",
            "message": "Upload failed",
        },
    ]
    (logs / "server.log").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    events = monitoring.read_timeline_events(logs)

    assert [event.message for event in events] == [
        "Server started",
        "Browser 192.168.1.32 connected",
        "Transfer failed: Upload failed",
    ]
    assert events[-1].kind == "transfer_failed"
    assert events[1].display_line().startswith("19:00")


def test_collect_android_device_details_uses_adb_metadata(monkeypatch, tmp_path: Path) -> None:
    device = AndroidDevice(
        serial="R58M123456",
        state="device",
        model="SM-G980F",
        connection_type="usb",
    )
    monkeypatch.setattr(monitoring, "_list_adb_devices", lambda _adb: [device])

    responses = {
        ("getprop", "ro.product.model"): "SM-G980F",
        ("getprop", "ro.product.manufacturer"): "samsung",
        ("getprop", "ro.build.version.release"): "13",
        ("getprop", "ro.build.version.sdk"): "33",
        ("wm", "size"): "Physical size: 1440x3200",
        ("dumpsys", "battery"): "level: 81\nscale: 100",
        ("dumpsys", "display"): "DisplayInfo{mDisplayId=0}",
        ("cat", "/proc/meminfo"): "MemAvailable:        3145728 kB",
    }

    def fake_shell(_adb: Path, serial: str, *args: str) -> str:
        assert serial == "R58M123456"
        return responses[args]

    monkeypatch.setattr(monitoring, "_adb_shell", fake_shell)

    details = monitoring.collect_android_device_details(tmp_path / "adb")

    assert details is not None
    assert details.model == "SM-G980F"
    assert details.manufacturer == "samsung"
    assert details.android_version == "13"
    assert details.api_level == "33"
    assert details.screen_resolution == "1440x3200"
    assert details.battery_percent == "81%"
    assert details.connection_type == "USB"
    assert details.physical_display_id == "0"
    assert details.available_ram == "3.0 GiB"


def test_unauthorized_device_details_do_not_run_shell(monkeypatch, tmp_path: Path) -> None:
    device = AndroidDevice(serial="blocked", state="unauthorized", connection_type="usb")
    monkeypatch.setattr(monitoring, "_list_adb_devices", lambda _adb: [device])
    monkeypatch.setattr(
        monitoring,
        "_adb_shell",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("shell should not run")),
    )

    details = monitoring.collect_android_device_details(tmp_path / "adb")

    assert details is not None
    assert details.serial == "blocked"
    assert details.adb_state == "unauthorized"
    assert details.android_version == "Unavailable"


def test_format_bytes_uses_binary_units() -> None:
    assert monitoring.format_bytes(1024) == "1.0 KiB"
    assert monitoring.format_bytes(3 * 1024**3) == "3.0 GiB"
