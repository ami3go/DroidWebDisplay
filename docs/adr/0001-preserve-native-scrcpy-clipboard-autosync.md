# ADR 0001: Preserve scrcpy native clipboard autosync

- Status: Accepted
- Date: 2026-08-19

## Context

DroidWebDisplay needs both automatic Android -> PC clipboard synchronization and deterministic manual Copy/Ctrl+C behavior.

A previous change added `clipboard_autosync=false` to scrcpy control sessions so explicit `GetClipboard` handling was easier to reason about. That solved one implementation concern but disabled scrcpy's normal Android primary-clipboard change notifications, causing Android -> PC synchronization to regress.

## Decision

Control sessions keep scrcpy native clipboard autosync enabled.

Manual Android Copy/Ctrl+C remains implemented independently through the browser-side explicit copy/write-through path.

The two behaviors are separate compatibility requirements and must not be traded against each other.

## Consequences

- Android clipboard changes continue to arrive through scrcpy's native listener.
- Manual Copy/Ctrl+C must tolerate the native listener behavior and must not depend on disabling it.
- Browser permission failures for PC clipboard reads must not disable Android -> PC synchronization.
- Tests must protect user-visible behavior and generated server arguments rather than merely checking source layout.

## Alternatives considered

### Disable scrcpy native autosync

Rejected because it removes automatic Android -> PC change notifications and caused the v0.11.6 regression.

### Replace native autosync with DroidWebDisplay polling

Possible future architecture, but not adopted now. It adds traffic/state management and must prove equal-or-better behavior across browser permission, reconnect, unchanged clipboard values, keyboard input, and physical/virtual display sessions.

## Replacement criteria

This decision may be superseded only when the replacement:

1. satisfies `docs/contracts/CLIPBOARD.md` completely;
2. preserves automatic and manual clipboard paths independently;
3. has behavioral regression coverage, preferably including HIL;
4. demonstrates equal-or-better reliability and maintainability;
5. does not introduce keyboard, focus, display, or reconnect regressions.
