from __future__ import annotations

import pytest

from droid_web_display.models import (
    DisplayImePolicy,
    DisplayMode,
    SessionOptions,
    VirtualDisplayOptions,
    VirtualDisplaySizeMode,
    VIRTUAL_DISPLAY_PROFILES,
)
from droid_web_display.scrcpy.command import build_server_arguments
from droid_web_display.scrcpy.virtual_display import (
    apply_device_virtual_display_compatibility,
    classify_virtual_display_failure,
    parse_new_display_line,
    virtual_display_capabilities,
)
from droid_web_display.models import AndroidDevice


def test_recommended_profile_and_server_mapping() -> None:
    virtual = VIRTUAL_DISPLAY_PROFILES["chatgpt-desktop"]
    options = SessionOptions(
        display_mode=DisplayMode.VIRTUAL,
        virtual_display=virtual,
        max_size=0,
        video_bit_rate=12_000_000,
        max_fps=60,
    )
    args = build_server_arguments("4.1", 0x12345678, options)
    assert "new_display=1600x900/240" in args
    assert "flex_display=false" not in args
    assert "vd_system_decorations=true" not in args
    assert "vd_destroy_content=true" not in args
    assert "cleanup=true" not in args
    assert "video_codec=h264" not in args
    assert "max_size=0" not in args
    assert "display_ime_policy=local" in args
    assert "keep_active=true" in args


def test_flex_and_default_ime_mapping() -> None:
    virtual = VirtualDisplayOptions(
        profile_id="custom",
        size_mode=VirtualDisplaySizeMode.FLEX,
        width=1280,
        height=960,
        dpi=200,
        start_app="com.example.app",
        ime_policy=DisplayImePolicy.DEFAULT,
    )
    args = build_server_arguments("4.1", 1, SessionOptions(display_mode=DisplayMode.VIRTUAL, virtual_display=virtual))
    assert "flex_display=true" in args
    assert not any(value.startswith("display_ime_policy=") for value in args)


def test_invalid_package_and_dimensions_are_rejected() -> None:
    with pytest.raises(ValueError, match="package"):
        VirtualDisplayOptions(start_app="bad package;rm").validate()
    with pytest.raises(ValueError, match="width"):
        VirtualDisplayOptions(width=320).validate()


def test_force_stop_payload_is_typed() -> None:
    virtual = VirtualDisplayOptions(start_app="com.openai.chatgpt", force_stop_before_launch=True)
    assert virtual.start_app_payload == "+com.openai.chatgpt"


def test_new_display_lifecycle_parser() -> None:
    value = parse_new_display_line("stdout: [server] INFO: New display: 1600x900/240 (id=4)")
    assert value is not None
    assert value.display_id == 4
    assert value.width == 1600
    assert value.height == 900
    assert value.dpi == 240


def test_capability_minimum_api() -> None:
    unsupported = virtual_display_capabilities(AndroidDevice("A", "device", sdk=28))
    supported = virtual_display_capabilities(AndroidDevice("B", "device", sdk=33), supported_codecs=["h264", "h265"])
    assert unsupported["virtualDisplaySupported"] is False
    assert supported["virtualDisplaySupported"] is True
    assert supported["supportedCodecs"] == ["h264", "h265"]


def test_samsung_android13_disables_local_ime_and_applies_default_fallback() -> None:
    device = AndroidDevice("S", "device", manufacturer="samsung", sdk=33)
    capabilities = virtual_display_capabilities(device)
    effective, warnings, fallback = apply_device_virtual_display_compatibility(
        device, VirtualDisplayOptions(ime_policy=DisplayImePolicy.LOCAL)
    )
    assert capabilities["localImePolicySupported"] is False
    assert effective.ime_policy == DisplayImePolicy.DEFAULT
    assert fallback is True
    assert warnings


def test_virtual_display_failure_classification_preserves_actionable_reason() -> None:
    assert classify_virtual_display_failure([
        "java.lang.SecurityException: Attempted to set IME policy to an untrusted virtual display"
    ]) == "ime-policy-rejected"
    assert classify_virtual_display_failure(["[server] ERROR: Could not create display"]) == "display-creation-failed"
    assert classify_virtual_display_failure([
        "stack corruption detected (-fstack-protector)",
        "Aborted",
    ]) == "app-process-stack-corruption"


def test_recommended_samsung_hil_arguments_match_upstream_compact_style() -> None:
    virtual = VirtualDisplayOptions(
        profile_id="chatgpt-desktop",
        width=1600,
        height=900,
        dpi=240,
        start_app="com.openai.chatgpt",
        ime_policy=DisplayImePolicy.DEFAULT,
    )
    args = build_server_arguments(
        "4.1",
        0x27520546,
        SessionOptions(
            display_mode=DisplayMode.VIRTUAL,
            virtual_display=virtual,
            max_size=0,
            video_bit_rate=12_000_000,
            max_fps=60,
            log_level="debug",
        ),
    )
    assert args == (
        "4.1",
        "scid=27520546",
        "log_level=debug",
        "video_bit_rate=12000000",
        "audio=false",
        "max_fps=60",
        "tunnel_forward=true",
        "new_display=1600x900/240",
        "keep_active=true",
    )
    assert len(args) == 9


def test_hide_ime_policy_is_virtual_display_only() -> None:
    virtual = VirtualDisplayOptions(ime_policy=DisplayImePolicy.HIDE)
    virtual_args = build_server_arguments(
        "4.1", 7, SessionOptions(display_mode=DisplayMode.VIRTUAL, virtual_display=virtual)
    )
    assert "display_ime_policy=hide" in virtual_args

    physical_args = build_server_arguments("4.1", 8, SessionOptions(display_mode=DisplayMode.PHYSICAL))
    assert not any(value.startswith("display_ime_policy=") for value in physical_args)
