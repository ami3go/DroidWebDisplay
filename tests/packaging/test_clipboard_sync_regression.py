from pathlib import Path


def test_automatic_clipboard_sync_does_not_request_paste() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "apps/web-client/src/controller.ts").read_text(encoding="utf-8")
    start = source.index("private async synchronizePcClipboard")
    end = source.index("private scheduleReconnect", start)
    block = source[start:end]
    assert "clipboardMessage(text, sequence, false)" in block
    assert "pasteText(text" not in block
    assert "paste=true" in block  # explanatory regression comment
