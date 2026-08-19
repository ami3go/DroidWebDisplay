from __future__ import annotations

import pytest

from droid_web_display.models import SessionOptions, SessionState
from droid_web_display.scrcpy.session import ScrcpySession, SessionManager, _optional_audio_relay_end


class DummyAdb:
    pass


def make_session(options: SessionOptions) -> ScrcpySession:
    return ScrcpySession(
        session_id="SESSION",
        serial="PHONE",
        scid=1,
        local_port=27183,
        socket_name="scrcpy_00000001",
        options=options,
        state=SessionState.RUNNING,
    )


def test_audio_relay_end_is_optional_only_when_other_channels_exist() -> None:
    normal = make_session(SessionOptions(video=True, audio=True, control=True))
    audio_only = make_session(SessionOptions(video=False, audio=True, control=False))

    assert _optional_audio_relay_end(normal, "browser_audio_device_eof") is True
    assert _optional_audio_relay_end(normal, "browser_audio_transport_error") is True
    assert _optional_audio_relay_end(normal, "browser_audio_authentication_revoked") is False
    assert _optional_audio_relay_end(normal, "browser_video_device_eof") is False
    assert _optional_audio_relay_end(audio_only, "browser_audio_device_eof") is False


@pytest.mark.asyncio
async def test_optional_audio_relay_end_does_not_stop_video_control_session() -> None:
    manager = SessionManager(DummyAdb())  # type: ignore[arg-type]
    session = make_session(SessionOptions(video=True, audio=True, control=True))
    manager._sessions[session.session_id] = session

    result = await manager.stop_session(session.session_id, reason="browser_audio_device_eof")

    assert result is session
    assert session.state == SessionState.RUNNING
    assert session.stop_reason is None
