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
        assert block.index("this.#lastSentClipboard = text") > block.index("if (await acknowledgement)")


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
        assert "beginAndroidCopyRequest" in block
        assert "completeAndroidCopyRequest" in block
        assert "Copy not confirmed" in block
        assert "previous PC clipboard was left unchanged" in block
        assert "writeText(this.#lastAndroidClipboard)" not in block


def test_android_copy_write_through_never_copies_stale_android_text() -> None:
    source, dist = _main_blocks()
    for block in (source, dist):
        assert "bindAndroidCopyWriteThrough" in block
        assert '"#clipboard-copy-android"' in block
        assert '"#screen"' in block
        assert "navigator.clipboard.writeText(text)" in block
        assert 'document.execCommand("copy")' in block
        assert 'currentStatus === "Clipboard received"' in block
        assert 'currentStatus === "Copy not confirmed"' in block
        assert "if (!responseObserved)" in block
        assert "previous PC clipboard was left unchanged" in block
        assert "No new Android clipboard event arrived; copied the last Android clipboard value." not in block
        assert "bindAndroidCopyWriteThrough();" in block


def test_manual_copy_timeout_clears_pending_and_late_clipboard_events_are_not_claimed() -> None:
    source, dist = _controller_blocks()
    src_helpers = source[source.index("\n  private beginAndroidCopyRequest"):source.index("\n  private async startClipboardPolling")]
    built_helpers = dist[dist.index("\n    beginAndroidCopyRequest"):dist.index("\n    async startClipboardPolling")]
    for block in (src_helpers, built_helpers):
        assert "#copyShortcutTimer" in block
        assert "#copyShortcutPending = false" in block
        assert "Copy not confirmed" in block
        assert "completeAndroidCopyRequest" in block

    for block in (source, dist):
        assert "const copyShortcut = this.completeAndroidCopyRequest();" in block


def test_clipboard_session_state_is_reset_before_use_and_on_cleanup() -> None:
    source, dist = _controller_blocks()
    for block in (source, dist):
        connect = block[block.index("this.#protocolSession = await this.#adapter.connect"):block.index("this.#deviceMessageTask = this.consumeDeviceMessages")]
        assert connect.index("resetClipboardSessionState()") < connect.index("setConnectedControls(true)")

        cleanup_start = block.index("async cleanupSession")
        cleanup_end = block.index("setConnectedControls", cleanup_start)
        cleanup = block[cleanup_start:cleanup_end]
        assert "resetClipboardSessionState()" in cleanup

        reset_start = block.index("resetClipboardSessionState()")
        reset_end = block.index("startClipboardPolling", reset_start)
        reset = block[reset_start:reset_end]
        assert '#lastAndroidClipboard = ""' in reset
        assert '#lastSentClipboard = ""' in reset
        assert 'clipboardText.value = ""' in reset
        assert "completeAndroidCopyRequest()" in reset


def test_failed_pc_clipboard_sync_remains_retryable() -> None:
    source, dist = _controller_blocks()
    src = source[source.index("\n  private async synchronizePcClipboard"):source.index("\n  private scheduleReconnect")]
    built = dist[dist.index("\n    async synchronizePcClipboard"):dist.index("\n    scheduleReconnect")]
    for block in (src, built):
        acknowledgement = block.index("if (await acknowledgement)")
        remembered = block.index("this.#lastSentClipboard = text")
        assert remembered > acknowledgement
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
