import pytest

from droid_web_display.models import ChannelName, SessionOptions
from droid_web_display.scrcpy.command import build_server_arguments, socket_name


def test_server_arguments_force_forward_and_keep_protocol_metadata() -> None:
    options = SessionOptions(audio=False, max_size=1280, max_fps=24)
    args = build_server_arguments("4.1", 0x1234ABCD, options)
    assert args[0] == "4.1"
    assert "scid=1234abcd" in args
    assert "tunnel_forward=true" in args
    assert "audio=false" in args
    assert "video_codec=h264" not in args
    assert "max_size=1280" in args
    assert "max_fps=24" in args
    assert not any(arg.startswith("raw_stream=") for arg in args)
    assert options.ordered_channels() == (ChannelName.VIDEO, ChannelName.CONTROL)


def test_selected_video_encoder_is_forwarded_without_changing_codec_default() -> None:
    options = SessionOptions(video_encoder="c2.exynos.avc.encoder", max_size=1280, max_fps=60)
    args = build_server_arguments("4.1", 0x10203040, options)
    assert "video_encoder=c2.exynos.avc.encoder" in args
    assert "video_codec=h264" not in args
    assert options.to_dict()["videoEncoder"] == "c2.exynos.avc.encoder"


def test_invalid_video_encoder_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="video_encoder"):
        SessionOptions(video_encoder="not a valid encoder name").validate()


def test_invalid_empty_channel_set_is_rejected() -> None:
    with pytest.raises(ValueError, match="At least one"):
        build_server_arguments("4.1", 1, SessionOptions(video=False, audio=False, control=False))


def test_scid_is_31_bit() -> None:
    assert socket_name(0x7FFFFFFF) == "scrcpy_7fffffff"
    with pytest.raises(ValueError):
        socket_name(0x80000000)


def test_audio_codec_and_bitrate_mapping() -> None:
    default_audio = build_server_arguments("4.1", 2, SessionOptions(audio=True))
    assert "audio=false" not in default_audio
    assert "audio_codec=opus" not in default_audio
    assert "audio_bit_rate=128000" not in default_audio

    aac = build_server_arguments("4.1", 3, SessionOptions(audio=True, audio_codec="aac", audio_bit_rate=96000))
    assert "audio_codec=aac" in aac
    assert "audio_bit_rate=96000" in aac
