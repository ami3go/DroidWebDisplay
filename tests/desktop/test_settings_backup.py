from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings

from droid_web_display.desktop.settings_backup import (
    desktop_settings_snapshot,
    export_desktop_settings,
    import_desktop_settings,
    reset_desktop_settings,
)


def _settings(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def test_export_import_and_reset_safe_desktop_settings(tmp_path: Path) -> None:
    source = _settings(tmp_path / "source.ini")
    source.setValue("openBrowserOnStart", False)
    source.setValue("notifyNewClient", False)
    source.setValue("updateChannel", "Pre-release")
    source.setValue("secretToken", "must-not-export")

    exported = export_desktop_settings(source, tmp_path / "settings.json")
    payload = json.loads(exported.read_text(encoding="utf-8"))

    assert payload["scope"] == "desktop-host-safe-settings"
    assert payload["settings"]["openBrowserOnStart"] is False
    assert payload["settings"]["updateChannel"] == "Pre-release"
    assert "secretToken" not in payload["settings"]

    target = _settings(tmp_path / "target.ini")
    imported = import_desktop_settings(target, exported)
    assert imported["notifyNewClient"] is False
    assert desktop_settings_snapshot(target)["updateChannel"] == "Pre-release"

    reset_desktop_settings(target)
    snapshot = desktop_settings_snapshot(target)
    assert snapshot["openBrowserOnStart"] is True
    assert snapshot["notifyNewClient"] is True
    assert snapshot["updateChannel"] == "Stable"


def test_import_rejects_unknown_update_channel(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps(
            {
                "formatVersion": 1,
                "application": "DroidWebDisplay",
                "settings": {"updateChannel": "Nightly"},
            }
        ),
        encoding="utf-8",
    )

    settings = _settings(tmp_path / "target.ini")
    try:
        import_desktop_settings(settings, path)
    except ValueError as exc:
        assert "Stable or Pre-release" in str(exc)
    else:
        raise AssertionError("invalid channel should have been rejected")
