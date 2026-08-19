from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / "apps/web-client/src/controller.ts"
MAIN = ROOT / "apps/web-client/src/main.ts"
TEST = ROOT / "tests/packaging/test_clipboard_sync_regression.py"


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_controller() -> None:
    text = CONTROLLER.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '  #clipboardPollBusy = false;\n  #copyShortcutPending = false;\n  #latestStatistics: VideoStatistics | null = null;',
        '  #clipboardPollBusy = false;\n  #copyShortcutPending = false;\n  #copyShortcutTimer: number | null = null;\n  #latestStatistics: VideoStatistics | null = null;',
        label="copy timeout field",
    )

    text = replace_once(
        text,
        '      this.#protocolSession = await this.#adapter.connect(this.#transport, {\n        video: true,\n        audio: this.elements.audioEnabled.checked,\n        control: true,\n      });\n      this.setConnectedControls(true);',
        '      this.#protocolSession = await this.#adapter.connect(this.#transport, {\n        video: true,\n        audio: this.elements.audioEnabled.checked,\n        control: true,\n      });\n      this.resetClipboardSessionState();\n      this.setConnectedControls(true);',
        label="session reset on connect",
    )

    text = replace_once(
        text,
        '    if (shortcut === "copy") {\n      event.preventDefault();\n      this.#copyShortcutPending = true;\n      await this.sendMessages([androidClipboardCopyMessage()]);\n      return;\n    }',
        '    if (shortcut === "copy") {\n      event.preventDefault();\n      this.beginAndroidCopyRequest("Ctrl+C");\n      await this.sendMessages([androidClipboardCopyMessage()]);\n      return;\n    }',
        label="Ctrl+C request lifecycle",
    )

    text = replace_once(
        text,
        '    if (new TextEncoder().encode(text).byteLength > maximum) throw new Error(`Clipboard text exceeds the configured ${maximum / 1024} KiB limit`);\n    this.#lastSentClipboard = text;\n    if (!session) return;',
        '    if (new TextEncoder().encode(text).byteLength > maximum) throw new Error(`Clipboard text exceeds the configured ${maximum / 1024} KiB limit`);\n    if (!session) return;',
        label="manual paste optimistic dedupe removal",
    )

    text = replace_once(
        text,
        '      if (await acknowledgement) {\n        this.setStatus("Text pasted", `${source} was injected directly and the Android clipboard synchronization was acknowledged.`);',
        '      if (await acknowledgement) {\n        this.#lastSentClipboard = text;\n        this.setStatus("Text pasted", `${source} was injected directly and the Android clipboard synchronization was acknowledged.`);',
        label="manual paste acknowledged dedupe",
    )

    text = replace_once(
        text,
        '        const copyShortcut = this.#copyShortcutPending;\n        this.#copyShortcutPending = false;',
        '        const copyShortcut = this.completeAndroidCopyRequest();',
        label="device-message copy completion",
    )

    text = replace_once(
        text,
        '    this.stopClipboardPolling();\n    this.#copyShortcutPending = false;\n    for (const sequence of [...this.#clipboardAcks.keys()]) this.resolveClipboardAcknowledgement(sequence, false);',
        '    this.stopClipboardPolling();\n    this.resetClipboardSessionState();\n    for (const sequence of [...this.#clipboardAcks.keys()]) this.resolveClipboardAcknowledgement(sequence, false);',
        label="session reset on cleanup",
    )

    old_copy = '''  private async copyAndroidClipboard(): Promise<void> {
    if (!this.#protocolSession) return;
    this.#copyShortcutPending = true;
    this.setStatus("Copying", "Requesting COPY from the focused Android selection…");
    await this.sendMessages([androidClipboardCopyMessage()]);
  }

  private async startClipboardPolling(requestPermission: boolean): Promise<void> {'''
    new_copy = '''  private async copyAndroidClipboard(): Promise<void> {
    if (!this.#protocolSession) return;
    this.beginAndroidCopyRequest("Copy");
    await this.sendMessages([androidClipboardCopyMessage()]);
  }

  private beginAndroidCopyRequest(source: string): void {
    if (this.#copyShortcutTimer !== null) window.clearTimeout(this.#copyShortcutTimer);
    this.#copyShortcutPending = true;
    this.#copyShortcutTimer = window.setTimeout(() => {
      this.#copyShortcutTimer = null;
      if (!this.#copyShortcutPending) return;
      this.#copyShortcutPending = false;
      if (!this.#protocolSession) return;
      this.setStatus("Copy not confirmed", `Android did not report a clipboard update for ${source}. The previous PC clipboard was left unchanged.`);
    }, 1_200);
    this.setStatus("Copying", `Requesting ${source} from the focused Android selection…`);
  }

  private completeAndroidCopyRequest(): boolean {
    const pending = this.#copyShortcutPending;
    this.#copyShortcutPending = false;
    if (this.#copyShortcutTimer !== null) window.clearTimeout(this.#copyShortcutTimer);
    this.#copyShortcutTimer = null;
    return pending;
  }

  private resetClipboardSessionState(): void {
    this.#lastAndroidClipboard = "";
    this.#lastSentClipboard = "";
    this.elements.clipboardText.value = "";
    this.completeAndroidCopyRequest();
  }

  private async startClipboardPolling(requestPermission: boolean): Promise<void> {'''
    text = replace_once(text, old_copy, new_copy, label="manual copy lifecycle helpers")

    text = replace_once(
        text,
        '    this.#lastSentClipboard = text;\n    const sequence = this.#clipboardSequence++;\n    // Automatic synchronization updates Android\'s clipboard only.',
        '    const sequence = this.#clipboardSequence++;\n    // Automatic synchronization updates Android\'s clipboard only.',
        label="automatic sync optimistic dedupe removal",
    )

    text = replace_once(
        text,
        '      if (await acknowledgement) {\n        this.setStatus("Clipboard synchronized", "PC clipboard was acknowledged by Android without pasting into the focused field.");',
        '      if (await acknowledgement) {\n        this.#lastSentClipboard = text;\n        this.setStatus("Clipboard synchronized", "PC clipboard was acknowledged by Android without pasting into the focused field.");',
        label="automatic sync acknowledged dedupe",
    )

    CONTROLLER.write_text(text, encoding="utf-8")


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '      const statusChanged = currentStatus !== initialStatus;\n      if ((textChanged || statusChanged) && currentStatus === "Clipboard copied") return;',
        '      const statusChanged = currentStatus !== initialStatus;\n      if (statusChanged && currentStatus === "Copy not confirmed") return;\n      if ((textChanged || statusChanged) && currentStatus === "Clipboard copied") return;',
        label="manual copy timeout observation",
    )
    text = replace_once(
        text,
        '    if (request !== generation) return;\n    const text = clipboardText.value;',
        '    if (request !== generation) return;\n    if (!responseObserved) {\n      status.textContent = "Copy not confirmed";\n      details.textContent = "Android did not return a new clipboard value. The previous PC clipboard was left unchanged.";\n      return;\n    }\n    const text = clipboardText.value;',
        label="manual copy stale-value rejection",
    )
    text = replace_once(
        text,
        '      details.textContent = responseObserved\n        ? "Android selection was copied to the PC clipboard."\n        : "No new Android clipboard event arrived; copied the last Android clipboard value.";',
        '      details.textContent = "Android selection was copied to the PC clipboard.";',
        label="manual copy stale success removal",
    )
    MAIN.write_text(text, encoding="utf-8")


def write_regression_tests() -> None:
    TEST.write_text('''from pathlib import Path


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
    src = source[source.index("\\n  private async pasteText"):source.index("\\n  private waitForClipboardAcknowledgement")]
    built = dist[dist.index("\\n    async pasteText"):dist.index("\\n    waitForClipboardAcknowledgement")]
    for block in (src, built):
        assert "clipboardMessage(text, sequence, false)" in block
        assert "textInjectionMessages(text)" in block
        assert "clipboardMessage(text, sequence, true)" not in block
        assert block.index("this.#lastSentClipboard = text") > block.index("if (await acknowledgement)")


def test_type_bypasses_clipboard_and_copy_requests_android_selection() -> None:
    source, dist = _controller_blocks()
    src_type = source[source.index("\\n  private async pasteTypedText"):source.index("\\n  private async pasteText")]
    built_type = dist[dist.index("\\n    async pasteTypedText"):dist.index("\\n    async pasteText")]
    for block in (src_type, built_type):
        assert "textInjectionMessages(text)" in block
        assert "pasteText(" not in block
        assert "clipboardMessage(" not in block

    src_copy = source[source.index("\\n  private async copyAndroidClipboard"):source.index("\\n  private async startClipboardPolling")]
    built_copy = dist[dist.index("\\n    async copyAndroidClipboard"):dist.index("\\n    async startClipboardPolling")]
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
    src_helpers = source[source.index("\\n  private beginAndroidCopyRequest"):source.index("\\n  private async startClipboardPolling")]
    built_helpers = dist[dist.index("\\n    beginAndroidCopyRequest"):dist.index("\\n    async startClipboardPolling")]
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
    src = source[source.index("\\n  private async synchronizePcClipboard"):source.index("\\n  private scheduleReconnect")]
    built = dist[dist.index("\\n    async synchronizePcClipboard"):dist.index("\\n    scheduleReconnect")]
    for block in (src, built):
        acknowledgement = block.index("if (await acknowledgement)")
        remembered = block.index("this.#lastSentClipboard = text")
        assert remembered > acknowledgement
        assert "clipboardMessage(text, sequence, false)" in block
        assert "pasteText(text" not in block
        assert "clipboardMessage(text, sequence, true)" not in block


def test_clipboard_permission_prompt_keeps_user_activation_and_drawer_does_not_force_textarea_focus() -> None:
    source, dist = _controller_blocks()
    src_poll = source[source.index("\\n  private async startClipboardPolling"):source.index("\\n  private stopClipboardPolling")]
    built_poll = dist[dist.index("\\n    async startClipboardPolling"):dist.index("\\n    stopClipboardPolling")]
    for block in (src_poll, built_poll):
        request = block.index("if (requestPermission)")
        read = block.index("navigator.clipboard.readText()", request)
        permissions = block.index("navigator.permissions?.query")
        assert request < read < permissions

    assert "this.elements.clipboardText.focus()" not in source
    assert "this.elements.clipboardText.focus()" not in dist
''', encoding="utf-8")


def main() -> None:
    patch_controller()
    patch_main()
    write_regression_tests()
    print("Clipboard hardening patch applied.")


if __name__ == "__main__":
    main()
