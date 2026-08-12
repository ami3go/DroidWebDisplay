from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from droid_web_display.profiles import (
    ConnectionProfileInput,
    ConnectionProfileStore,
    ProfileConflictError,
    ProfileNotFoundError,
)


def profile_input(name: str = "S20 Daily") -> ConnectionProfileInput:
    return ConnectionProfileInput.model_validate({
        "name": name,
        "device": {"serial": "R58N123456A", "model": "SM-G980F"},
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
        "audio": {"enabled": False, "muted": False, "volume": 85},
        "clipboard": {"automatic": False, "maximumKiB": 128},
        "reconnect": {"enabled": True, "attempts": 5},
        "video": {"encoderMode": "auto", "encoder": None},
    })


def test_store_crud_default_and_atomic_document(tmp_path: Path) -> None:
    path = tmp_path / "connection-profiles.json"
    store = ConnectionProfileStore(path)
    created = store.create(profile_input())
    assert created.name == "S20 Daily"
    assert path.is_file()
    assert not path.with_suffix(".json.tmp").exists()

    document = store.list()
    assert [item.id for item in document.profiles] == [created.id]
    assert document.default_profile_id is None

    assert store.set_default(created.id) == created.id
    assert store.list().default_profile_id == created.id

    updated = store.update(created.id, profile_input("S20 Daily Updated"))
    assert updated.created_at == created.created_at
    assert updated.updated_at >= created.updated_at
    assert updated.name == "S20 Daily Updated"

    used = store.mark_used(created.id)
    assert used.last_used_at is not None

    store.delete(created.id)
    assert store.list().profiles == []
    assert store.list().default_profile_id is None
    with pytest.raises(ProfileNotFoundError):
        store.get(created.id)

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schemaVersion"] == 1
    assert raw["profiles"] == []


def test_store_rejects_duplicate_names_case_insensitively(tmp_path: Path) -> None:
    store = ConnectionProfileStore(tmp_path / "profiles.json")
    store.create(profile_input("S20 Daily"))
    with pytest.raises(ProfileConflictError):
        store.create(profile_input("s20 daily"))


def test_profile_schema_rejects_security_and_runtime_state() -> None:
    payload = profile_input().model_dump(by_alias=True, mode="json")
    payload["pin"] = "123456"
    with pytest.raises(ValidationError):
        ConnectionProfileInput.model_validate(payload)

    payload = profile_input().model_dump(by_alias=True, mode="json")
    payload["network"] = {"mode": "lan-https"}
    with pytest.raises(ValidationError):
        ConnectionProfileInput.model_validate(payload)


def test_selected_encoder_requires_name_and_auto_forbids_name() -> None:
    payload = profile_input().model_dump(by_alias=True, mode="json")
    payload["video"] = {"encoderMode": "selected", "encoder": None}
    with pytest.raises(ValidationError):
        ConnectionProfileInput.model_validate(payload)

    payload["video"] = {"encoderMode": "auto", "encoder": "c2.exynos.avc.encoder"}
    with pytest.raises(ValidationError):
        ConnectionProfileInput.model_validate(payload)


def test_reconnect_attempts_match_the_production_selector() -> None:
    for value in (3, 5, 10):
        payload = profile_input().model_dump(by_alias=True, mode="json")
        payload["reconnect"]["attempts"] = value
        assert ConnectionProfileInput.model_validate(payload).reconnect.attempts == value

    for invalid in (1, 4, 20):
        payload = profile_input().model_dump(by_alias=True, mode="json")
        payload["reconnect"]["attempts"] = invalid
        with pytest.raises(ValidationError):
            ConnectionProfileInput.model_validate(payload)
