from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


PROFILE_SCHEMA_VERSION = 1
PROFILE_STORE_SCHEMA_VERSION = 1
MAX_PROFILES = 100
_DEVICE_SERIAL_PATTERN = r"^[A-Za-z0-9._:-]+$"
_ENCODER_PATTERN = r"^[A-Za-z0-9._:+-]+$"
_PACKAGE_PATTERN = r"^(?:[A-Za-z][A-Za-z0-9_]*)(?:\.[A-Za-z][A-Za-z0-9_]*)+$"


class ProfileError(RuntimeError):
    """Base error for persisted connection profiles."""


class ProfileNotFoundError(ProfileError):
    pass


class ProfileConflictError(ProfileError):
    pass


class ProfileStoreError(ProfileError):
    pass


class ProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ProfileDevice(ProfileModel):
    serial: str = Field(min_length=1, max_length=255, pattern=_DEVICE_SERIAL_PATTERN)
    model: str | None = Field(default=None, max_length=160)


class ProfileDisplay(ProfileModel):
    display_mode: Literal["physical", "virtual"] = Field(alias="displayMode")
    profile_id: str = Field(default="custom", alias="profileId", min_length=1, max_length=80)
    size_mode: Literal["fixed", "flex"] = Field(default="fixed", alias="sizeMode")
    width: int = Field(default=1600, ge=640, le=3840)
    height: int = Field(default=900, ge=480, le=2160)
    dpi: int = Field(default=240, ge=120, le=640)
    start_app: str = Field(default="com.openai.chatgpt", alias="startApp", max_length=255)
    force_stop_before_launch: bool = Field(default=False, alias="forceStopBeforeLaunch")
    keep_active: bool = Field(default=True, alias="keepActive")
    system_decorations: bool = Field(default=True, alias="systemDecorations")
    destroy_content_on_close: bool = Field(default=True, alias="destroyContentOnClose")
    ime_policy: Literal["default", "local", "fallback", "hide"] = Field(default="local", alias="imePolicy")
    preserve_aspect_ratio: bool = Field(default=True, alias="preserveAspectRatio")
    video_bit_rate_mbps: float = Field(default=10.0, alias="videoBitRateMbps", ge=2, le=50)
    max_fps: int = Field(default=60, alias="maxFps", ge=15, le=120)

    @model_validator(mode="after")
    def validate_virtual_application(self) -> "ProfileDisplay":
        if self.start_app and not __import__("re").fullmatch(_PACKAGE_PATTERN, self.start_app):
            raise ValueError("startApp must be an exact Android package name")
        if self.display_mode == "virtual" and not self.start_app and not self.system_decorations:
            raise ValueError("startApp is required when virtual system decorations are disabled")
        return self


class ProfileAudio(ProfileModel):
    enabled: bool = False
    muted: bool = False
    volume: int = Field(default=100, ge=0, le=100)


class ProfileClipboard(ProfileModel):
    automatic: bool = False
    maximum_kib: int = Field(default=256, alias="maximumKiB", ge=1, le=256)


class ProfileReconnect(ProfileModel):
    enabled: bool = True
    attempts: int = Field(default=5, ge=1, le=20)


class ProfileVideo(ProfileModel):
    encoder_mode: Literal["auto", "selected"] = Field(default="auto", alias="encoderMode")
    encoder: str | None = Field(default=None, max_length=255, pattern=_ENCODER_PATTERN)

    @model_validator(mode="after")
    def validate_encoder_mode(self) -> "ProfileVideo":
        if self.encoder_mode == "selected" and not self.encoder:
            raise ValueError("encoder is required when encoderMode is selected")
        if self.encoder_mode == "auto" and self.encoder is not None:
            raise ValueError("encoder must be null when encoderMode is auto")
        return self


class ConnectionProfileInput(ProfileModel):
    name: str = Field(min_length=1, max_length=80)
    device: ProfileDevice
    display: ProfileDisplay
    audio: ProfileAudio = Field(default_factory=ProfileAudio)
    clipboard: ProfileClipboard = Field(default_factory=ProfileClipboard)
    reconnect: ProfileReconnect = Field(default_factory=ProfileReconnect)
    video: ProfileVideo = Field(default_factory=ProfileVideo)

    @model_validator(mode="after")
    def trim_name(self) -> "ConnectionProfileInput":
        cleaned = " ".join(self.name.split())
        if not cleaned:
            raise ValueError("profile name cannot be blank")
        object.__setattr__(self, "name", cleaned)
        return self


class StoredConnectionProfile(ConnectionProfileInput):
    schema_version: Literal[1] = Field(default=PROFILE_SCHEMA_VERSION, alias="schemaVersion")
    id: str = Field(min_length=1, max_length=64)
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")
    last_used_at: str | None = Field(default=None, alias="lastUsedAt")


class ProfileDocument(ProfileModel):
    schema_version: Literal[1] = Field(default=PROFILE_STORE_SCHEMA_VERSION, alias="schemaVersion")
    default_profile_id: str | None = Field(default=None, alias="defaultProfileId")
    profiles: list[StoredConnectionProfile] = Field(default_factory=list)


class ConnectionProfileStore:
    """Atomic server-side persistence for named connection profiles."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self._lock = threading.RLock()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _read(self) -> ProfileDocument:
        if not self.path.is_file():
            return ProfileDocument()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            document = ProfileDocument.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ProfileStoreError(f"Connection profile store is unreadable: {self.path}") from exc
        ids = [profile.id for profile in document.profiles]
        if len(ids) != len(set(ids)):
            raise ProfileStoreError("Connection profile store contains duplicate IDs")
        if document.default_profile_id and document.default_profile_id not in ids:
            # Recover safely from a deleted/hand-edited default pointer without losing profiles.
            document.default_profile_id = None
        return document

    def _write(self, document: ProfileDocument) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = document.model_dump(by_alias=True, mode="json")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _profile_index(document: ProfileDocument, profile_id: str) -> int:
        for index, profile in enumerate(document.profiles):
            if profile.id == profile_id:
                return index
        raise ProfileNotFoundError(f"Connection profile was not found: {profile_id}")

    @staticmethod
    def _ensure_name_available(document: ProfileDocument, name: str, *, exclude_id: str | None = None) -> None:
        folded = name.casefold()
        if any(profile.id != exclude_id and profile.name.casefold() == folded for profile in document.profiles):
            raise ProfileConflictError(f"A connection profile named '{name}' already exists")

    def list(self) -> ProfileDocument:
        with self._lock:
            return self._read().model_copy(deep=True)

    def get(self, profile_id: str) -> StoredConnectionProfile:
        with self._lock:
            document = self._read()
            return document.profiles[self._profile_index(document, profile_id)].model_copy(deep=True)

    def create(self, value: ConnectionProfileInput) -> StoredConnectionProfile:
        with self._lock:
            document = self._read()
            if len(document.profiles) >= MAX_PROFILES:
                raise ProfileConflictError(f"At most {MAX_PROFILES} connection profiles may be stored")
            self._ensure_name_available(document, value.name)
            timestamp = self._now()
            profile = StoredConnectionProfile(
                **value.model_dump(),
                id=uuid4().hex,
                createdAt=timestamp,
                updatedAt=timestamp,
                lastUsedAt=None,
            )
            document.profiles.append(profile)
            self._write(document)
            return profile.model_copy(deep=True)

    def update(self, profile_id: str, value: ConnectionProfileInput) -> StoredConnectionProfile:
        with self._lock:
            document = self._read()
            index = self._profile_index(document, profile_id)
            previous = document.profiles[index]
            self._ensure_name_available(document, value.name, exclude_id=profile_id)
            profile = StoredConnectionProfile(
                **value.model_dump(),
                id=profile_id,
                createdAt=previous.created_at,
                updatedAt=self._now(),
                lastUsedAt=previous.last_used_at,
            )
            document.profiles[index] = profile
            self._write(document)
            return profile.model_copy(deep=True)

    def delete(self, profile_id: str) -> None:
        with self._lock:
            document = self._read()
            index = self._profile_index(document, profile_id)
            del document.profiles[index]
            if document.default_profile_id == profile_id:
                document.default_profile_id = None
            self._write(document)

    def set_default(self, profile_id: str | None) -> str | None:
        with self._lock:
            document = self._read()
            if profile_id is not None:
                self._profile_index(document, profile_id)
            document.default_profile_id = profile_id
            self._write(document)
            return document.default_profile_id

    def mark_used(self, profile_id: str) -> StoredConnectionProfile:
        with self._lock:
            document = self._read()
            index = self._profile_index(document, profile_id)
            profile = document.profiles[index]
            updated = profile.model_copy(update={"last_used_at": self._now()})
            document.profiles[index] = updated
            self._write(document)
            return updated.model_copy(deep=True)
