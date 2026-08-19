# Clipboard Compatibility Contract

Status: **Protected**

Clipboard behavior is a cross-cutting compatibility contract. Changes to scrcpy server arguments, control messages, browser clipboard code, keyboard shortcuts, focus handling, reconnect logic, or virtual-display session startup must preserve every requirement below.

## Required behavior matrix

| Behavior | Requirement |
|---|---|
| Android copy -> PC clipboard automatically | Must work |
| Android -> PC Copy button | Must work |
| Android -> PC Ctrl+C | Must work |
| PC clipboard -> Android automatic sync | Must work when browser permission allows it |
| PC -> Android Paste button | Must work |
| PC -> Android Ctrl+V | Must work |
| Typed-text fallback | Must work when browser clipboard permission is unavailable |
| Normal PC keyboard typing | Must remain usable while clipboard sync is enabled |
| Repeated/same Android clipboard value | Manual Copy must still be able to copy it |
| Browser permission failure | Must not disable Android -> PC clipboard flow |
| Physical display | Must not be altered as a side effect of virtual-display clipboard/input work |

## Current architecture

### Android -> PC automatic synchronization

```text
Android ClipboardManager
    -> scrcpy native clipboard listener
    -> scrcpy Device Clipboard message
    -> DroidWebDisplay control protocol
    -> web client clipboard handler
    -> PC/browser clipboard when permission and user-agent policy allow it
```

Control sessions intentionally keep scrcpy's native clipboard autosync enabled. The server arguments must not disable this path with `clipboard_autosync=false` unless a replacement implements equivalent Android -> PC change notification behavior and has behavioral regression coverage.

### Android -> PC manual Copy / Ctrl+C

```text
Copy button or Ctrl+C
    -> explicit clipboard request / current Android clipboard value
    -> browser-side write-through
    -> Clipboard API or fallback copy path
```

The manual path exists independently of automatic synchronization. Manual Copy must continue to work even when the Android clipboard text has not changed since the previous notification.

### PC -> Android

```text
PC/browser clipboard or typed text
    -> permission-gated browser read or manual text
    -> scrcpy SetClipboard/control path
    -> Android ClipboardManager
```

Automatic PC -> Android synchronization depends on browser clipboard-read permission. Permission failure in this direction must not stop Android -> PC synchronization.

## Critical invariant

**The automatic Android -> PC path and the explicit/manual Android -> PC Copy path are independent requirements. A fix for one must not disable or weaken the other.**

Do not solve a manual Copy problem by disabling scrcpy native clipboard autosync.

Do not solve browser permission problems by blocking keyboard input or repeatedly prompting/focusing a paste UI.

## Regression history

In v0.11.6, `clipboard_autosync=false` was added to control sessions to make direct `GetClipboard` behavior deterministic. That also disabled normal Android clipboard-change notifications and broke Android -> PC synchronization. The regression was fixed by restoring scrcpy native clipboard autosync while retaining the browser-side manual Copy/Ctrl+C fallback.

This history is an architectural warning: implementation-level fixes must be evaluated against the full behavior matrix, not only the immediate failing path.

## Required tests

At minimum, code changes in this area should preserve automated checks that verify:

- control sessions do not disable native clipboard autosync;
- non-control sessions still disable the control channel correctly;
- manual Android Copy behavior remains present;
- browser clipboard permission handling does not trigger background permission prompts;
- clipboard automation does not block normal typing;
- release/web-client tests remain green.

When HIL coverage is available, the preferred end-to-end tests are:

1. Put unique text in the Android clipboard and verify it reaches the PC/browser.
2. Repeat manual Copy with the same unchanged clipboard value.
3. Copy new PC text and verify Android receives it.
4. Deny browser clipboard-read permission and verify Android -> PC still works.
5. Type normally with automatic synchronization enabled and verify no paste dialog/focus loop blocks input.

## Replacement criteria

This architecture may be changed only when the replacement:

- satisfies the complete behavior matrix above;
- has equal-or-better reliability;
- includes behavioral regression coverage;
- documents the new flow and migration rationale;
- does not weaken physical-display or keyboard behavior.
