from types import SimpleNamespace

import pytest

import droid_web_display.runtime_hardening as hardening
from droid_web_display.models import SessionOptions
from droid_web_display.scrcpy.encoder_tuning import configure_encoder_tuning


@pytest.mark.asyncio
async def test_stale_saved_encoder_falls_back_to_scrcpy_auto(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = configure_encoder_tuning(tmp_path / "video-encoder-tuning.json")
    store.set_preference("PHONE", "encoder.stale")
    attempted: list[str | None] = []
    display_names: list[str | None] = []

    async def fake_start_session(self, *, serial=None, options=None, display_name=None):
        del self, serial
        attempted.append(options.video_encoder)
        display_names.append(display_name)
        if options.video_encoder is not None:
            raise RuntimeError("Android rejected persisted encoder")
        return SimpleNamespace(server_log=[])

    monkeypatch.setattr(hardening._BaseSessionManager, "start_session", fake_start_session)
    manager = object.__new__(hardening.ResilientSessionManager)

    session = await manager.start_session(
        serial="PHONE",
        options=SessionOptions(),
        display_name="ChatGPT",
    )

    assert attempted == ["encoder.stale", None]
    assert display_names == ["ChatGPT", "ChatGPT"]
    assert store.preference("PHONE") is None
    assert store.last_invalidation("PHONE") == "preferred-encoder-start-failed"
    assert "retried successfully with scrcpy auto" in session.server_log[-1]


@pytest.mark.asyncio
async def test_explicit_per_session_encoder_does_not_silently_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    configure_encoder_tuning(tmp_path / "video-encoder-tuning.json")
    attempted: list[str | None] = []

    async def fake_start_session(self, *, serial=None, options=None, display_name=None):
        del self, serial
        attempted.append(options.video_encoder)
        raise RuntimeError("explicit encoder failed")

    monkeypatch.setattr(hardening._BaseSessionManager, "start_session", fake_start_session)
    manager = object.__new__(hardening.ResilientSessionManager)

    with pytest.raises(RuntimeError, match="explicit encoder failed"):
        await manager.start_session(
            serial="PHONE",
            options=SessionOptions(video_encoder="encoder.explicit"),
        )

    assert attempted == ["encoder.explicit"]
