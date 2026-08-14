from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings

from droid_web_display import __version__


SETTING_DEFAULTS: dict[str, object] = {
    "openBrowserOnStart": True,
    "startMinimized": False,
    "selectedTab": 0,
    "notifyAndroid": True,
    "notifyServerFailure": True,
    "notifyUnauthorized": True,
    "notifyNewClient": True,
    "notifyTransferFailure": True,
    "updateChannel": "Stable",
}


def _typed_value(settings: QSettings, key: str, default: object) -> object:
    if isinstance(default, bool):
        return settings.value(key, default, type=bool)
    if isinstance(default, int):
        return settings.value(key, default, type=int)
    return str(settings.value(key, default))


def desktop_settings_snapshot(settings: QSettings) -> dict[str, object]:
    return {
        key: _typed_value(settings, key, default)
        for key, default in SETTING_DEFAULTS.items()
    }


def export_desktop_settings(settings: QSettings, target: Path) -> Path:
    target = target.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "formatVersion": 1,
        "application": "DroidWebDisplay",
        "applicationVersion": __version__,
        "scope": "desktop-host-safe-settings",
        "settings": desktop_settings_snapshot(settings),
    }
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def _validate_setting(key: str, value: Any, default: object) -> object:
    if isinstance(default, bool):
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be true or false")
        return value
    if isinstance(default, int):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{key} must be an integer")
        return value
    if not isinstance(value, str):
        raise ValueError(f"{key} must be text")
    if key == "updateChannel" and value not in {"Stable", "Pre-release"}:
        raise ValueError("updateChannel must be Stable or Pre-release")
    return value


def import_desktop_settings(settings: QSettings, source: Path) -> dict[str, object]:
    source = source.expanduser().resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Settings file must contain a JSON object")
    if payload.get("application") != "DroidWebDisplay":
        raise ValueError("This is not a DroidWebDisplay settings file")
    if payload.get("formatVersion") != 1:
        raise ValueError("Unsupported DroidWebDisplay settings format")
    values = payload.get("settings")
    if not isinstance(values, dict):
        raise ValueError("Settings file does not contain a settings object")

    imported: dict[str, object] = {}
    for key, default in SETTING_DEFAULTS.items():
        if key not in values:
            continue
        imported[key] = _validate_setting(key, values[key], default)

    for key, value in imported.items():
        settings.setValue(key, value)
    settings.sync()
    return imported


def reset_desktop_settings(settings: QSettings) -> None:
    for key in SETTING_DEFAULTS:
        settings.remove(key)
    settings.sync()
