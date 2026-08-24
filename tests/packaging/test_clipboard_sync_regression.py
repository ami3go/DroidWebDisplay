import re
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
        assert "CLIPBOARD_STATUS.notConfirmed" in block
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
        # These sentinels are the contract between controller.ts and main.ts.
        # They live in clipboard-status.ts precisely so that rewording one at a
        # call site cannot silently break the Copy button; assert on the shared
        # symbol, and pin the literal values in the dedicated test below.
        assert "currentStatus === CLIPBOARD_STATUS.received" in block
        assert "currentStatus === CLIPBOARD_STATUS.notConfirmed" in block
        assert "if (!responseObserved)" in block
        assert "previous PC clipboard was left unchanged" in block
        assert "bindAndroidCopyWriteThrough();" in block

        copy_binding = block[block.index("function bindAndroidCopyWriteThrough"):block.index("function browserGpuRenderer")]
        assert 'document.addEventListener("keydown"' in copy_binding
        assert "isEditableTarget(event.target)" in copy_binding
        assert "!selection.isCollapsed" in copy_binding
        assert 'canvas.addEventListener("keydown"' not in copy_binding


def test_manual_copy_suppresses_only_the_expected_native_autosync_duplicate() -> None:
    root = Path(__file__).resolve().parents[2]
    guard_source = (root / "apps/web-client/src/clipboard-events.ts").read_text(encoding="utf-8")
    guard_dist = (root / "apps/web-client/dist/assets/clipboard-events.js").read_text(encoding="utf-8")
    controller_source, controller_dist = _controller_blocks()
    for block in (guard_source, guard_dist):
        assert "ManualCopyDuplicateGuard" in block
        assert "this.reset()" in block
    for block in (controller_source, controller_dist):
        assert "#manualCopyDuplicate.consume(message.text, performance.now())" in block
        assert "#manualCopyDuplicate.arm(message.text, performance.now())" in block
        assert "#manualCopyDuplicate.reset()" in block


def test_manual_copy_timeout_clears_pending_and_late_clipboard_events_are_not_claimed() -> None:
    source, dist = _controller_blocks()
    src_helpers = source[source.index("\n  private beginAndroidCopyRequest"):source.index("\n  private async startClipboardPolling")]
    built_helpers = dist[dist.index("\n    beginAndroidCopyRequest"):dist.index("\n    async startClipboardPolling")]
    for block in (src_helpers, built_helpers):
        assert "#copyShortcutTimer" in block
        assert "#copyShortcutPending = false" in block
        assert "CLIPBOARD_STATUS.notConfirmed" in block
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

    src_reset_start = source.index("\n  private resetClipboardSessionState(): void {")
    src_reset_end = source.index("\n  private async startClipboardPolling", src_reset_start)
    built_reset_start = dist.index("\n    resetClipboardSessionState() {")
    built_reset_end = dist.index("\n    async startClipboardPolling", built_reset_start)
    for reset in (source[src_reset_start:src_reset_end], dist[built_reset_start:built_reset_end]):
        assert '#lastAndroidClipboard = ""' in reset
        assert '#lastSentClipboard = ""' in reset
        assert "#unacknowledgedSync = null" in reset
        assert "#manualCopyDuplicate.reset()" in reset
        assert "completeAndroidCopyRequest()" in reset
        # The visible text box is user input, not cached device state. Clearing
        # it on connect discards text typed while disconnected.
        assert 'clipboardText.value = ""' not in reset


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
        # Retryable, but bounded: pollPcClipboard runs every 1800ms and skips
        # only text recorded as sent, so an unbounded retry re-sends the same
        # text every tick for as long as it stays on the PC clipboard.
        assert "MAX_UNACKNOWLEDGED_SYNC_ATTEMPTS" in block
        assert "#unacknowledgedSync" in block
        gave_up = block.index("Clipboard sync gave up")
        assert block.index("this.#lastSentClipboard = text", gave_up - 400) < gave_up


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


def test_oversized_text_is_synchronized_rather_than_typed_chunk_by_chunk() -> None:
    source, dist = _controller_blocks()
    src = source[source.index("\n  private async pasteText"):source.index("\n  private waitForClipboardAcknowledgement")]
    built = dist[dist.index("\n    async pasteText"):dist.index("\n    waitForClipboardAcknowledgement")]
    for block in (src, built):
        # textInjectionMessages chunks at 300 UTF-8 bytes and each chunk is an
        # awaited control message, so injecting a 256 KiB clipboard would be
        # roughly 875 sequential round trips.
        assert "MAX_INJECTED_BYTES" in block
        assert re.search(r"if \(inject\)\s+await this\.sendMessages\(textInjectionMessages\(text\)\)", block)

    src_type = source[source.index("\n  private async pasteTypedText"):source.index("\n  private async pasteText")]
    built_type = dist[dist.index("\n    async pasteTypedText"):dist.index("\n    async pasteText")]
    for block in (src_type, built_type):
        assert "MAX_INJECTED_BYTES" in block
        assert "too large to type into Android" in block


def test_clipboard_status_sentinels_are_defined_once_and_shared() -> None:
    """The copy write-through matches these strings against the status line.

    Rewording one at a call site used to break the Copy button with a green
    suite, so the literals now live in one module and both sides import them.
    """
    root = Path(__file__).resolve().parents[2]
    contract = (root / "apps/web-client/src/clipboard-status.ts").read_text(encoding="utf-8")
    built = (root / "apps/web-client/dist/assets/clipboard-status.js").read_text(encoding="utf-8")
    for block in (contract, built):
        assert 'copying: "Copying"' in block
        assert 'copied: "Clipboard copied"' in block
        assert 'received: "Clipboard received"' in block
        assert 'notConfirmed: "Copy not confirmed"' in block

    controller = (root / "apps/web-client/src/controller.ts").read_text(encoding="utf-8")
    main = (root / "apps/web-client/src/main.ts").read_text(encoding="utf-8")
    for block in (controller, main):
        assert 'from "./clipboard-status.js"' in block
    # No call site may restate a sentinel as a literal.
    for literal in ('setStatus("Clipboard received"', 'setStatus("Copy not confirmed"', 'setStatus("Copying"'):
        assert literal not in controller
