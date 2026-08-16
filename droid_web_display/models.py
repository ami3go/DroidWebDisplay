from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class DeviceState(StrEnum):
    DEVICE = "device"
    UNAUTHORIZED = "unauthorized"
    OFFLINE = "offline"
    BOOTLOADER = "bootloader"
    HOST = "host"
    RECOVERY = "recovery"
    RESCUE = "rescue"
    SIDELOAD = "sideload"
    AUTHORIZING = "authorizing"
    CONNECTING = "connecting"
    DETACHED = "detached"
    NO_PERMISSIONS = "no permissions"
    UNKNOWN = "unknown"


READY_DEVICE_STATE = DeviceState.DEVICE.value


@dataclass(frozen=True)
class AndroidDevice:
    serial: str
    state: str
    model: str | None = None
    product: str | None = None
    device: str | None = None
    transport_id: str | None = None
    usb: str | None = None
    manufacturer: str | None = None
    android_version: str | None = None
    sdk: int | None = None
    connection_type: str = "unknown"
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def ready(self) -> bool:
        return self.state == READY_DEVICE_STATE

    @property
    def authorization_required(self) -> bool:
        return self.state in {
            DeviceState.UNAUTHORIZED.value,
            DeviceState.AUTHORIZING.value,
        }

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["ready"] = self.ready
        result["authorizationRequired"] = self.authorization_required
        return result


class SessionState(StrEnum):
    IDLE = "idle"
    PROBING = "probing"
    STARTING = "starting"
    CREATING_DISPLAY = "creating-display"
    LAUNCHING_APP = "launching-app"
    CONNECTING_VIDEO = "connecting-video"
    CONNECTING_CONTROL = "connecting-control"
    RUNNING = "running"
    RESIZING = "resizing"
    STOPPING = "stopping"
    STOPPED = "stopped"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


class ChannelName(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    CONTROL = "control"


class DisplayMode(StrEnum):
    PHYSICAL = "physical"
    VIRTUAL = "virtual"


class VirtualDisplaySizeMode(StrEnum):
    FIXED = "fixed"
    FLEX = "flex"


class DisplayImePolicy(StrEnum):
    DEFAULT = "default"
    LOCAL = "local"
    FALLBACK = "fallback"
    HIDE = "hide"


_PACKAGE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z][a-zA-Z0-9_]*)+$")


@dataclass(frozen=True)
class VirtualDisplayOptions:
    profile_id: str = "chatgpt-desktop"
    size_mode: VirtualDisplaySizeMode = VirtualDisplaySizeMode.FIXED
    width: int = 1600
    height: int = 900
    dpi: int = 240
    start_app: str = "com.openai.chatgpt"
    force_stop_before_launch: bool = False
    keep_active: bool = True
    system_decorations: bool = True
    destroy_content_on_close: bool = True
    ime_policy: DisplayImePolicy = DisplayImePolicy.LOCAL
    preserve_aspect_ratio: bool = True

    def validate(self) -> None:
        if not 640 <= self.width <= 3840:
            raise ValueError("virtual display width must be between 640 and 3840")
        if not 480 <= self.height <= 2160:
            raise ValueError("virtual display height must be between 480 and 2160")
        if not 120 <= self.dpi <= 640:
            raise ValueError("virtual display DPI must be between 120 and 640")
        if self.width > 0xFFFF or self.height > 0xFFFF:
            raise ValueError("virtual display dimensions must fit the scrcpy uint16 resize protocol")
        if self.start_app and not _PACKAGE_RE.fullmatch(self.start_app):
            raise ValueError("startApp must be an exact Android package name")
        if not self.start_app and not self.system_decorations:
            raise ValueError("startApp is required when virtual-display system decorations are disabled")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", self.profile_id):
            raise ValueError("profileId contains unsupported characters")

    @property
    def flex_display(self) -> bool:
        return self.size_mode == VirtualDisplaySizeMode.FLEX

    @property
    def start_app_payload(self) -> str:
        if not self.start_app:
            return ""
        return f"+{self.start_app}" if self.force_stop_before_launch else self.start_app

    def to_dict(self) -> dict[str, Any]:
        return {
            "profileId": self.profile_id,
            "sizeMode": self.size_mode.value,
            "width": self.width,
            "height": self.height,
            "dpi": self.dpi,
            "startApp": self.start_app,
            "forceStopBeforeLaunch": self.force_stop_before_launch,
            "keepActive": self.keep_active,
            "systemDecorations": self.system_decorations,
            "destroyContentOnClose": self.destroy_content_on_close,
            "imePolicy": self.ime_policy.value,
            "preserveAspectRatio": self.preserve_aspect_ratio,
        }


VIRTUAL_DISPLAY_PROFILES: dict[str, VirtualDisplayOptions] = {
    "chatgpt-desktop": VirtualDisplayOptions(),
    "full-hd-desktop": VirtualDisplayOptions(
        profile_id="full-hd-desktop",
        width=1920,
        height=1080,
    ),
    "low-bandwidth": VirtualDisplayOptions(
        profile_id="low-bandwidth",
        width=1280,
        height=720,
        dpi=200,
    ),
    "flexible-window": VirtualDisplayOptions(
        profile_id="flexible-window",
        size_mode=VirtualDisplaySizeMode.FLEX,
        width=1280,
        height=960,
        dpi=200,
    ),
}


@dataclass(frozen=True)
class SessionOptions:
    video: bool = True
    audio: bool = False
    control: bool = True
    audio_codec: str = "opus"
    audio_bit_rate: int = 128_000
    video_codec: str = "h264"
    max_size: int = 1920
    video_bit_rate: int = 8_000_000
    max_fps: int = 30
    log_level: str = "info"
    cleanup: bool = True
    display_mode: DisplayMode = DisplayMode.PHYSICAL
    virtual_display: VirtualDisplayOptions | None = None

    def validate(self) -> None:
        if not (self.video or self.audio or self.control):
            raise ValueError("At least one scrcpy channel must be enabled")
        if self.audio_codec not in {"opus", "aac", "flac", "raw"}:
            raise ValueError("audio_codec must be opus, aac, flac or raw")
        if not 16_000 <= self.audio_bit_rate <= 512_000:
            raise ValueError("audio_bit_rate must be between 16 Kbps and 512 Kbps")
        if self.video_codec not in {"h264", "h265", "av1"}:
            raise ValueError("video_codec must be h264, h265 or av1")
        if self.max_size < 0:
            raise ValueError("max_size must be zero or positive")
        if not 2_000_000 <= self.video_bit_rate <= 50_000_000:
            raise ValueError("video_bit_rate must be between 2 Mbps and 50 Mbps")
        if not 15 <= self.max_fps <= 120:
            raise ValueError("max_fps must be between 15 and 120")
        if self.display_mode == DisplayMode.VIRTUAL:
            if not self.video or not self.control:
                raise ValueError("Virtual Display mode requires video and control channels")
            if self.virtual_display is None:
                raise ValueError("virtualDisplay configuration is required in Virtual Display mode")
            self.virtual_display.validate()
        elif self.virtual_display is not None:
            # Preserve the object for UI round-trips but do not apply it in physical mode.
            self.virtual_display.validate()

    def ordered_channels(self) -> tuple[ChannelName, ...]:
        channels: list[ChannelName] = []
        if self.video:
            channels.append(ChannelName.VIDEO)
        if self.audio:
            channels.append(ChannelName.AUDIO)
        if self.control:
            channels.append(ChannelName.CONTROL)
        return tuple(channels)

    def to_dict(self) -> dict[str, Any]:
        return {
            "video": self.video,
            "audio": self.audio,
            "control": self.control,
            "audioCodec": self.audio_codec,
            "audioBitRate": self.audio_bit_rate,
            "videoCodec": self.video_codec,
            "maxSize": self.max_size,
            "videoBitRate": self.video_bit_rate,
            "maxFps": self.max_fps,
            "displayMode": self.display_mode.value,
            "virtualDisplay": self.virtual_display.to_dict() if self.virtual_display else None,
        }
