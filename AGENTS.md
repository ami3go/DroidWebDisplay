# DroidWebDisplay Agent Instructions

## Primary rule: preserve working behavior

DroidWebDisplay is maintained as a continuously working application. Existing working user-visible behavior is a compatibility contract.

When implementing a feature, fixing a bug, refactoring, updating dependencies, or changing architecture:

- Do not remove or degrade existing functionality as a side effect.
- Do not replace a working mechanism merely because another implementation is simpler.
- Architecture may be replaced only when the replacement is demonstrably equal or better in functionality, reliability, and maintainability.
- A change that fixes one feature but breaks another is not acceptable.
- Add a regression test for every fixed bug when practical.
- Prefer behavioral tests over source-text assertions or tests that merely encode the current implementation.
- Never change a regression test only to make a new implementation pass if the user-visible contract is being weakened.

Read `docs/STABILITY_CONTRACT.md` before broad refactors or cross-cutting changes.

## Protected subsystems

Treat these as regression-sensitive:

- Android <-> PC clipboard
- keyboard input and Ctrl+C / Ctrl+V
- browser focus and clipboard permission handling
- scrcpy control protocol and server arguments
- physical and virtual display behavior
- physical-display isolation from virtual-display options
- video startup, reconnect, rotation, and resizing
- file transfer
- Windows background process handling
- packaged Windows and Linux runtimes

A change touching scrcpy session arguments, control messages, WebSocket/session startup, browser input, clipboard code, or virtual-display configuration must be reviewed for effects on all related protected behaviors.

## Clipboard rules

Before changing clipboard, keyboard, browser-focus, scrcpy control, or session-argument code, read `docs/contracts/CLIPBOARD.md`.

The following are independent requirements and must all remain functional:

1. Android -> PC automatic clipboard synchronization.
2. Android -> PC manual Copy / Ctrl+C.
3. PC -> Android automatic synchronization when browser permission allows it.
4. PC -> Android manual Paste / Ctrl+V / Type fallbacks.
5. Normal keyboard typing must remain usable while clipboard synchronization is enabled.

Do not solve one clipboard direction by disabling another.

In particular, control sessions currently rely on scrcpy native clipboard autosync for Android -> PC change notifications. Do not pass `clipboard_autosync=false` unless a replacement provides equivalent behavior and has behavioral regression coverage.

## Required validation

Before merging a change that touches protected subsystems:

1. Run the complete release gate.
2. Run relevant regression tests.
3. Run web-client tests when browser/control behavior changes.
4. Run Windows package smoke tests for packaged-runtime changes.
5. Run Linux AppImage smoke tests for packaged-runtime changes.
6. Do not merge with known functional regressions.

For architecture replacement, also update the relevant contract/ADR and explain why the replacement is equal-or-better.

## Documentation map

- Current architecture: `docs/ARCHITECTURE.md`
- Stability policy: `docs/STABILITY_CONTRACT.md`
- Clipboard contract: `docs/contracts/CLIPBOARD.md`
- Architecture decisions: `docs/adr/`
- Clipboard/UX notes: `docs/UX_AUDIO_CLIPBOARD.md`
- Virtual display: `docs/VIRTUAL_DISPLAY.md`
