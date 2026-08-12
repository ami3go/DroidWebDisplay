from __future__ import annotations

from pathlib import Path
import re

from droid_web_display.models import (
    INTERACTIVE_MAX_FPS,
    INTERACTIVE_PHYSICAL_MAX_SIZE,
    INTERACTIVE_VIDEO_BIT_RATE,
    SessionOptions,
)


ROOT = Path(__file__).resolve().parents[2]


def test_backend_session_defaults_use_interactive_envelope() -> None:
    options = SessionOptions()
    assert options.max_size == INTERACTIVE_PHYSICAL_MAX_SIZE == 1600
    assert options.video_bit_rate == INTERACTIVE_VIDEO_BIT_RATE == 10_000_000
    assert options.max_fps == INTERACTIVE_MAX_FPS == 60
    assert options.video_codec == "h264"


def test_web_and_backend_interactive_defaults_cannot_drift() -> None:
    source = (ROOT / "apps" / "web-client" / "src" / "display-config.ts").read_text(encoding="utf-8")
    match = re.search(
        r"export const PHYSICAL_DISPLAY_DEFAULTS = Object\.freeze\(\{(?P<body>.*?)\}\);",
        source,
        flags=re.DOTALL,
    )
    assert match is not None
    body = match.group("body")
    assert 'videoCodec: "h264"' in body
    assert f"maxSize: {INTERACTIVE_PHYSICAL_MAX_SIZE}" in body
    assert f"videoBitRate: {INTERACTIVE_VIDEO_BIT_RATE:_}" in body
    assert f"maxFps: {INTERACTIVE_MAX_FPS}" in body
    assert "...PHYSICAL_DISPLAY_DEFAULTS" in source
