from pathlib import Path


def _controller_blocks() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[2]
    source = (root / "apps/web-client/src/controller.ts").read_text(encoding="utf-8")
    dist = (root / "apps/web-client/dist/assets/controller.js").read_text(encoding="utf-8")
    return source, dist


def _main_blocks() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[2]
    source = (root / "apps/web-client/src/main.ts").read_text(encoding="utf-8")
    dist = (root / "apps/web-client/dist/assets/main.js").read_text(encoding="utf-8")
    return source, dist


def test_manual_paste_synchronizes_without_android_paste_key_and_injects_text() -> None:
    source, dist = _controller_blocks()
    src = source[source.index("\n  private async pasteText"):source.index("\n  private waitForClipboardAcknowledgement")]
    built = dist[dist.index("\n    async pasteText"):dist.index("\n    waitForClipboardAcknowledgement")]
    for block in (src, built):
        assert "clipboardMessage(text, sequence, false)" in block
        assert "textInjectionMessages(text)" in block
        assert "clipboardMessage(text, sequence, true)" not in block


def test_type_bypasses_clipboard_and_copy_requests_android_selection() -> None:
    source, dist = _controller_blocks()
    src_type = source[source.index("\n  private async pasteTypedText"):source.index("\n  private async pasteText")]
    built_type = dist[dist.index("\n    async pasteTypedText"):dist.index("\n    async pasteText")]
    for block in (src_type, built_type):
        assert "textInjectionMessages(text)" in block
        assert "pasteText(" not in block
        assert "clipboardMessage(" not in block

    src_copy = source[source.index("\n  private async copyAndroidClipboard"):source.index("\n  private async startClipboardPolling")]
    built_copy = dist[dist.index("\n    async copyAndroidClipboard"):dist.index("\n    async startClipboardPolling")]
    for block in (src_copy, built_copy):
        assert "androidClipboardCopyMessage()" in block
        assert "writeText(this.#lastAndroidClipboard)" not in block


def test_android_copy_write_through_preserves_browser_user_activation() -> None:
    source, dist = _main_blocks()
    for block in (source, dist):
        assert "bindAndroidCopyWriteThrough" in block
        assert '"#clipboard-copy-android"' in block
        assert '"#screen"' in block
        assert "navigator.clipboard.writeText(text)" in block
        assert 'document.execCommand("copy")' in block
        assert 'currentStatus === "Clipboard received"' in block
        assert "bindAndroidCopyWriteThrough();" in block


def test_automatic_clipboard_sync_does_not_request_paste() -> None:
    source, dist = _controller_blocks()
    src = source[source.index("\n  private async synchronizePcClipboard"):source.index("\n  private scheduleReconnect")]
    built = dist[dist.index("\n    async synchronizePcClipboard"):dist.index("\n    scheduleReconnect")]
    for block in (src, built):
        assert "clipboardMessage(text, sequence, false)" in block
        assert "pasteText(text" not in block
        assert "clipboardMessage(text, sequence, true)" not in block


def test_clipboard_permission_prompt_keeps_user_activation_and_drawer_does_not_force_textarea_focus() -> None:
    source, dist = _controller_blocks()
    src_poll = source[source.index("\n  private async startClipboardPolling"):source.index("\n  private stopClipboardPolling")]
    built_poll = dist[dist.index("\n    async startClipboardPolling"):dist.index("\n    stopClipboardPolling")]
    for block in (src_poll, built_poll):
        request = block.index("if (requestPermission)")
        read = block.index("navigator.clipboard.readText()", request)
        permissions = block.index("navigator.permissions?.query")
        assert request < read < permissions

    assert "this.elements.clipboardText.focus()" not in source
    assert "this.elements.clipboardText.focus()" not in dist
