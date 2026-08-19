from __future__ import annotations

from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected text not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


input_path = Path("apps/web-client/src/input.ts")
input_text = input_path.read_text(encoding="utf-8")
controller_path = Path("apps/web-client/src/controller.ts")
controller = controller_path.read_text(encoding="utf-8")

already_fixed = (
    "androidClipboardReadMessage" in input_text
    and "#androidClipboardPollTimer" in controller
    and "pollAndroidClipboard" in controller
)
if already_fixed:
    print("Android clipboard polling fix already present")
    raise SystemExit(0)

replace_once(
    str(input_path),
    '''export function androidClipboardCopyMessage(): ControlMessage {\n  return { type: ControlMessageType.GetClipboard, copyKey: 1 } as ControlMessage;\n}\n\nexport function keyboardMessages''',
    '''export function androidClipboardCopyMessage(): ControlMessage {\n  return { type: ControlMessageType.GetClipboard, copyKey: 1 } as ControlMessage;\n}\n\nexport function androidClipboardReadMessage(): ControlMessage {\n  return { type: ControlMessageType.GetClipboard, copyKey: 0 } as ControlMessage;\n}\n\nexport function keyboardMessages''',
)

controller = controller_path.read_text(encoding="utf-8")
old_import = 'import { androidClipboardCopyMessage, androidKeyPress, clipboardMessage, clipboardShortcut, keyboardMessages, mapClientPoint, textInjectionMessages } from "./input.js";'
new_import = 'import { androidClipboardCopyMessage, androidClipboardReadMessage, androidKeyPress, clipboardMessage, clipboardShortcut, keyboardMessages, mapClientPoint, textInjectionMessages } from "./input.js";'
if old_import not in controller:
    raise SystemExit("controller input import shape changed")
controller = controller.replace(old_import, new_import, 1)

old_field = "  #clipboardPollTimer: number | null = null;\n  #clipboardReadAllowed = false;"
new_field = "  #clipboardPollTimer: number | null = null;\n  #androidClipboardPollTimer: number | null = null;\n  #clipboardReadAllowed = false;"
if old_field not in controller:
    raise SystemExit("controller clipboard field shape changed")
controller = controller.replace(old_field, new_field, 1)

polling_pattern = re.compile(
    r"  private async startClipboardPolling\(requestPermission: boolean\): Promise<void> \{.*?(?=  private async synchronizePcClipboard\(text: string\): Promise<void> \{)",
    re.S,
)
polling_replacement = '''  private async startClipboardPolling(requestPermission: boolean): Promise<void> {\n    this.stopClipboardPolling();\n    this.#clipboardReadAllowed = false;\n    if (!this.#protocolSession || !this.elements.clipboardAutoSync.checked) return;\n\n    if (!navigator.clipboard?.readText) {\n      this.startAndroidClipboardPolling();\n      this.setStatus("Clipboard sync limited", "This browser cannot read the PC clipboard automatically. Android → PC synchronization remains available.");\n      return;\n    }\n\n    const armPolling = async (initial: string): Promise<void> => {\n      this.#clipboardReadAllowed = true;\n      if (initial && initial !== this.#lastSentClipboard && initial !== this.#lastAndroidClipboard) {\n        await this.synchronizePcClipboard(initial);\n      }\n      this.#clipboardPollTimer = window.setInterval(() => void this.pollPcClipboard(), 1800);\n      this.startAndroidClipboardPolling();\n    };\n\n    if (requestPermission) {\n      try {\n        // Keep this as the first awaited browser API call from the checkbox gesture.\n        await armPolling(await navigator.clipboard.readText());\n      } catch {\n        this.#clipboardReadAllowed = false;\n        this.startAndroidClipboardPolling();\n        this.setStatus("Clipboard sync limited", "Browser clipboard permission was not granted. Use Paste or Type manually; Android → PC synchronization remains active.");\n      }\n      return;\n    }\n\n    let permissionState: PermissionState | "unsupported" = "unsupported";\n    if (navigator.permissions?.query) {\n      try {\n        const permission = await navigator.permissions.query({ name: "clipboard-read" as PermissionName });\n        permissionState = permission.state;\n      } catch {\n        // Some browsers expose Clipboard but not clipboard-read through Permissions.\n      }\n    }\n\n    if (permissionState === "denied") {\n      this.startAndroidClipboardPolling();\n      this.setStatus("Clipboard sync limited", "Automatic PC → Android clipboard access is blocked by the browser. Use Paste or Type manually; Android → PC sync remains active.");\n      return;\n    }\n    if (permissionState !== "granted") {\n      this.startAndroidClipboardPolling();\n      this.setStatus("Clipboard sync ready", "Android → PC sync is active. Toggle automatic sync off/on once to grant PC → Android clipboard access.");\n      return;\n    }\n\n    try {\n      await armPolling(await navigator.clipboard.readText());\n    } catch {\n      this.#clipboardReadAllowed = false;\n      this.startAndroidClipboardPolling();\n      this.setStatus("Clipboard sync limited", "Browser clipboard permission was not granted. Use Paste or Type manually; Android → PC synchronization remains active.");\n    }\n  }\n\n  private stopClipboardPolling(): void {\n    if (this.#clipboardPollTimer !== null) window.clearInterval(this.#clipboardPollTimer);\n    if (this.#androidClipboardPollTimer !== null) window.clearInterval(this.#androidClipboardPollTimer);\n    this.#clipboardPollTimer = null;\n    this.#androidClipboardPollTimer = null;\n    this.#clipboardPollBusy = false;\n  }\n\n  private startAndroidClipboardPolling(): void {\n    if (!this.#protocolSession || !this.elements.clipboardAutoSync.checked) return;\n    void this.pollAndroidClipboard();\n    this.#androidClipboardPollTimer = window.setInterval(() => void this.pollAndroidClipboard(), 1200);\n  }\n\n  private async pollAndroidClipboard(): Promise<void> {\n    if (!this.#protocolSession || !this.elements.clipboardAutoSync.checked) return;\n    await this.sendMessages([androidClipboardReadMessage()]);\n  }\n\n  private async pollPcClipboard(): Promise<void> {\n    if (!document.hasFocus() || !this.#protocolSession || !this.elements.clipboardAutoSync.checked || !this.#clipboardReadAllowed || this.#clipboardPollBusy) return;\n    this.#clipboardPollBusy = true;\n    try {\n      const text = await navigator.clipboard.readText();\n      if (!text || text === this.#lastSentClipboard || text === this.#lastAndroidClipboard) return;\n      await this.synchronizePcClipboard(text);\n    } catch {\n      // Stop only PC reads. Android → PC polling must remain active.\n      this.#clipboardReadAllowed = false;\n      if (this.#clipboardPollTimer !== null) window.clearInterval(this.#clipboardPollTimer);\n      this.#clipboardPollTimer = null;\n      this.setStatus("Clipboard sync limited", "Automatic PC clipboard access stopped after a browser permission error. Android → PC synchronization remains active; use Paste manually or toggle sync to grant PC access again.");\n    } finally {\n      this.#clipboardPollBusy = false;\n    }\n  }\n\n'''
controller, count = polling_pattern.subn(polling_replacement, controller, count=1)
if count != 1:
    raise SystemExit(f"Expected one clipboard polling block, replaced {count}")

old_receive = '''        this.#lastAndroidClipboard = message.text;\n        this.elements.clipboardText.value = message.text;\n        const copyShortcut = this.#copyShortcutPending;\n        this.#copyShortcutPending = false;\n        if (this.elements.clipboardAutoSync.checked || copyShortcut) {'''
new_receive = '''        const changed = message.text !== this.#lastAndroidClipboard;\n        this.#lastAndroidClipboard = message.text;\n        this.elements.clipboardText.value = message.text;\n        const copyShortcut = this.#copyShortcutPending;\n        this.#copyShortcutPending = false;\n        if (!changed && !copyShortcut) continue;\n        if (this.elements.clipboardAutoSync.checked || copyShortcut) {'''
if old_receive not in controller:
    raise SystemExit("controller Android clipboard receive block changed")
controller = controller.replace(old_receive, new_receive, 1)
controller_path.write_text(controller, encoding="utf-8")

# Unit test the non-copy-key GetClipboard message.
test_input = Path("apps/web-client/tests/input.test.mjs")
text = test_input.read_text(encoding="utf-8")
old = 'import { androidClipboardCopyMessage, androidKeyPress, clipboardMessage, clipboardShortcut, keyboardMessages, mapClientPoint, textInjectionMessages } from "../dist/assets/input.js";'
new = 'import { androidClipboardCopyMessage, androidClipboardReadMessage, androidKeyPress, clipboardMessage, clipboardShortcut, keyboardMessages, mapClientPoint, textInjectionMessages } from "../dist/assets/input.js";'
if old not in text:
    raise SystemExit("input test import shape changed")
text = text.replace(old, new, 1)
marker = '  assert.deepEqual(androidClipboardCopyMessage(), { type: 8, copyKey: 1 });\n});'
replacement = '  assert.deepEqual(androidClipboardCopyMessage(), { type: 8, copyKey: 1 });\n  assert.deepEqual(androidClipboardReadMessage(), { type: 8, copyKey: 0 });\n});'
if marker not in text:
    raise SystemExit("input clipboard assertion shape changed")
test_input.write_text(text.replace(marker, replacement, 1), encoding="utf-8")

# Static regression coverage for independent Android polling.
layout = Path("apps/web-client/tests/layout.test.mjs")
text = layout.read_text(encoding="utf-8")
marker = '''test("automatic clipboard polling never prompts from the background", () => {\n  assert.match(controllerSource, /startClipboardPolling\\(requestPermission: boolean\\)/);\n  assert.match(controllerSource, /if \\(requestPermission\\)/);\n  assert.match(controllerSource, /permissionState !== "granted"/);\n  assert.match(controllerSource, /#clipboardReadAllowed/);\n  assert.match(controllerSource, /Stop polling after the first runtime permission failure/);\n});\n'''
replacement = '''test("automatic clipboard polling keeps Android to PC independent of PC read permission", () => {\n  assert.match(controllerSource, /startClipboardPolling\\(requestPermission: boolean\\)/);\n  assert.match(controllerSource, /startAndroidClipboardPolling\\(\\)/);\n  assert.match(controllerSource, /pollAndroidClipboard\\(\\)[\\s\\S]*androidClipboardReadMessage\\(\\)/);\n  assert.match(controllerSource, /#androidClipboardPollTimer/);\n  const pcPoll = controllerSource.slice(controllerSource.indexOf("private async pollPcClipboard"), controllerSource.indexOf("private async synchronizePcClipboard"));\n  assert.doesNotMatch(pcPoll, /stopClipboardPolling\\(\\)/);\n  assert.match(pcPoll, /Android → PC synchronization remains active/);\n});\n'''
if marker not in text:
    raise SystemExit("layout clipboard polling test shape changed")
layout.write_text(text.replace(marker, replacement, 1), encoding="utf-8")

packaging = Path("tests/packaging/test_clipboard_sync_regression.py")
text = packaging.read_text(encoding="utf-8")
insert_before = '\ndef test_clipboard_permission_prompt_keeps_user_activation_and_drawer_does_not_force_textarea_focus() -> None:\n'
addition = '''\ndef test_android_to_pc_autosync_polls_scrcpy_independently_of_pc_clipboard_permission() -> None:\n    source, dist = _controller_blocks()\n    for block in (source, dist):\n        assert "androidClipboardReadMessage()" in block\n        assert "#androidClipboardPollTimer" in block\n        assert "startAndroidClipboardPolling()" in block\n        pc_poll = block[block.index("pollPcClipboard"):block.index("synchronizePcClipboard", block.index("pollPcClipboard"))]\n        assert "stopClipboardPolling()" not in pc_poll\n        assert "Android → PC synchronization remains active" in pc_poll\n\n'''
if insert_before not in text:
    raise SystemExit("packaging regression insertion point changed")
packaging.write_text(text.replace(insert_before, addition + insert_before, 1), encoding="utf-8")

# Make the release gate explicitly cover this direction too.
gate = Path("tools/release_gate.py")
text = gate.read_text(encoding="utf-8")
old = '        "synchronizePcClipboard", "clipboardMessage(text, sequence, false)",\n        "if (requestPermission)", \'permissionState !== "granted"\', "#clipboardReadAllowed",\n'
new = '        "synchronizePcClipboard", "clipboardMessage(text, sequence, false)",\n        "pollAndroidClipboard", "androidClipboardReadMessage", "#androidClipboardPollTimer",\n        "if (requestPermission)", \'permissionState !== "granted"\', "#clipboardReadAllowed",\n'
if old not in text:
    raise SystemExit("release gate clipboard token shape changed")
gate.write_text(text.replace(old, new, 1), encoding="utf-8")

print("Applied Android → PC clipboard polling regression fix")
