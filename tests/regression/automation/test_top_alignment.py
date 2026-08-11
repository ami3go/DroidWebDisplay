from pathlib import Path


def test_android_stage_is_top_aligned() -> None:
    root = Path(__file__).resolve().parents[3]
    css = (root / "apps/web-client/static/styles.css").read_text(encoding="utf-8")
    assert ".stage { align-items: start; justify-items: center; }" in css
    assert ".stage:fullscreen { align-items: start; justify-items: center; }" in css
