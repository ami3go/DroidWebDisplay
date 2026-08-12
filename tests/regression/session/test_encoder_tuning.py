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


def test_encoder_tuning_auto_uses_fastest_successful_benchmark(tmp_path: Path) -> None:
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
    assert store.recommended("PHONE") == "encoder.fast"

    restored = EncoderTuningStore(path)
    assert restored.recommended("PHONE") == "encoder.fast"
    restored.set_preference("PHONE", "encoder.slow")
    assert restored.recommended("PHONE") == "encoder.slow"
    restored.set_preference("PHONE", None)
    assert restored.recommended("PHONE") == "encoder.fast"
