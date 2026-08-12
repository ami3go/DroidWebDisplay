from pathlib import Path

from droid_web_display.scrcpy.encoder_tuning import (
    EncoderBenchmarkResult,
    EncoderTuningStore,
    parse_h264_encoders,
)


def test_h264_encoder_discovery_prefers_hardware_candidates() -> None:
    text = """
      component c2.android.avc.encoder rank=512
      component OMX.Exynos.AVC.Encoder rank=256
      component c2.exynos.avc.encoder rank=128
      component c2.android.hevc.encoder rank=512
      component OMX.google.h264.encoder rank=1024
    """
    values = parse_h264_encoders(text)
    assert values[:2] == ["c2.exynos.avc.encoder", "OMX.Exynos.AVC.Encoder"]
    assert "c2.android.hevc.encoder" not in values
    assert values[-1] in {"c2.android.avc.encoder", "OMX.google.h264.encoder"}


def test_startup_compatibility_does_not_auto_select_encoder(tmp_path: Path) -> None:
    path = tmp_path / "video-encoder-tuning.json"
    store = EncoderTuningStore(path)
    store.set_benchmark_results(
        "PHONE",
        [
            EncoderBenchmarkResult("encoder.slow", True, 140.0),
            EncoderBenchmarkResult("encoder.failed", False, 50.0, "failed"),
            EncoderBenchmarkResult("encoder.fast", True, 72.5),
        ],
    )

    # Startup timing includes ADB/server/tunnel setup and is therefore only
    # compatibility evidence, not an interactive latency ranking.
    assert store.recommended("PHONE") is None
    assert store.compatible_encoders("PHONE") == ["encoder.slow", "encoder.fast"]

    restored = EncoderTuningStore(path)
    assert restored.recommended("PHONE") is None
    restored.set_preference("PHONE", "encoder.slow")
    assert restored.recommended("PHONE") == "encoder.slow"
    restored.set_preference("PHONE", None)
    assert restored.recommended("PHONE") is None


def test_android_build_change_invalidates_cached_tuning(tmp_path: Path) -> None:
    store = EncoderTuningStore(tmp_path / "video-encoder-tuning.json")
    assert store.bind_device("PHONE", "build/one") is False
    store.set_discovered_encoders("PHONE", ["encoder.hw"])
    store.set_preference("PHONE", "encoder.hw")
    store.set_benchmark_results("PHONE", [EncoderBenchmarkResult("encoder.hw", True, 80.0)])

    assert store.bind_device("PHONE", "build/two") is True
    assert store.preference("PHONE") is None
    assert store.cached_encoders("PHONE") == []
    assert store.benchmark_results("PHONE") == []
    assert store.last_invalidation("PHONE") == "android-build-changed"
