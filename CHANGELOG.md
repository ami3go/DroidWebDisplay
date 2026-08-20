# Changelog

## 0.11.7 — Clipboard reliability fix

- Restored normal Android → PC clipboard synchronization by keeping scrcpy native clipboard autosync enabled for control sessions.
- Hardened manual Android Copy and Ctrl+C so an expired request cannot copy stale clipboard text or claim a later unrelated Android clipboard event.
- Reset clipboard dedupe and pending-copy state when sessions disconnect, reconnect, or start again.
- Remember PC → Android clipboard values only after Android acknowledges them, so failed synchronization remains retryable instead of being incorrectly deduplicated.
- Preserved non-pasting automatic synchronization (`SetClipboard(paste=false)`) so clipboard sync does not interfere with normal keyboard typing.
- Added regression coverage for stale-copy rejection, copy timeout cleanup, reconnect/session reset, and retry after an unconfirmed clipboard synchronization.

## 0.11.6 — Windows console flash fix

- Fixed the Windows packaged application repeatedly opening and immediately closing console windows while the server was running.
- Applied `CREATE_NO_WINDOW` consistently to background ADB commands and the scrcpy server child process, matching the existing hidden-process behavior used by the desktop host.
- Centralized the Windows subprocess creation flags so future ADB call sites inherit the same GUI-safe launch behavior.
- Added regression coverage verifying both ordinary ADB commands and scrcpy server startup pass the hidden-window creation flags.

## 0.11.5 — Clipboard reliability and compact header refinements

- Fixed PC → Android text transfer end to end: **Type** now uses direct scrcpy text injection, while **Paste** and **Ctrl+V** synchronize the Android clipboard without depending on Android's `KEYCODE_PASTE` behavior and then inject the text deterministically.
- Fixed Android → PC **Copy** and **Ctrl+C** by disabling scrcpy's native clipboard autosync for controlled sessions so `GetClipboard(COPY)` returns clipboard data deterministically instead of depending on Android's primary-clipboard change listener.
- Fixed browser clipboard handling so drawer focus and permission flows no longer break Ctrl+V or normal keyboard input, and added a browser-side copy fallback for restricted clipboard-write contexts.
- Refined the header into compact icon-only Android controls and a DroidWebDisplay brand/status lockup with clearer phone/display connection-state presentation.
- Merged Health information into Overview and corrected Settings/tab sizing and scrolling regressions.
- Added regression coverage for clipboard semantics in both directions, header/status layout, power controls, and release/static asset consistency.

## 0.11.4 — Screen drop target, clipboard paste fix, and correctness pass

- Added a drag-and-drop upload target on the mirrored screen: files dropped anywhere over the Android display are queued to the server's configured inbox directory, without navigating to the Files drawer. The Explorer drop zone is unchanged.
- Fixed Ctrl+V pasting to Android only while the canvas held keyboard focus. The paste listener now sits on the document, so it works regardless of which control was clicked last, while the fallback textarea and other inputs still paste into themselves.
- Removed the unreachable Ctrl+V keydown branch, and corrected the release gate and two test suites that had been pinning that dead branch in place.
- Fixed a bounded-retention gap where baselined and PC-uploaded watched files were never trimmed, so the auto-download tables grew without limit.
- Fixed mid-command ADB pipe failures escaping as unhandled 500s instead of a mapped ADB-unavailable error.
- Fixed the desktop status probe flipping a shutting-down server back to "running" and re-enabling its controls.
- Fixed the transfer destination guard being a no-op on Windows, where system folders such as `C:\Windows\System32` passed as download destinations.
- Fixed scrcpy session retention not applying to sessions that failed during startup.
- Bounded ADB Sync writes and the manual auto-download scan so neither can hang indefinitely.
- Rate-limited every PIN check reachable from the API, and made first-run setup roll back cleanly on failure.

## 0.11.2 — Unified page scrolling

- Removed the independent vertical scrollbar from the right-side transfer panel.
- Both left and right card columns now scroll with the single browser/page scrollbar.
- Top-aligned workspace grid items so a tall side panel does not stretch the Android display stage vertically.
- Added browser and release-gate regression coverage for the single-scrollbar layout.

## 0.11.1 — Clipboard shortcuts and virtual-display keyboard suppression

- Restored explicit Ctrl+V paste handling without reintroducing automatic-paste behavior.
- Added Ctrl+C remote-copy handling through scrcpy GetClipboard/Copy.
- Added a virtual-display-only checkbox to hide the Android on-screen keyboard.
- Physical phone-screen mode never emits a display IME policy and remains unaffected.

## 0.11.0 — Packaging, migration, and clipboard-sync reliability

- Fixed automatic PC-to-Android clipboard synchronization so it updates the Android clipboard with `paste=false`; automatic sync no longer repeatedly triggers Android paste UI or blocks normal PC keyboard typing.
- Added platform release-tree generation for Windows, Linux, and source bundles with deterministic version/component manifests.
- Added SHA-256 verification of the pinned scrcpy server during packaging.
- Added optional bundled adb, Python runtime, and offline wheelhouse inputs with an explicit offline-readiness gate.
- Added Windows and Linux install/uninstall launchers with data-preserving upgrade behavior.
- Added supported configuration migration for authentication, network-access, monitor state, and TLS material.
- Added license layout, package inventory validation, runtime-state/private-key leak checks, and packaging regression tests.

## 0.10.2 — UI layout corrections

- Fixed the Display Mode collapse button being stretched by the card-wide button rule; collapse controls are now compact 1.25 rem square buttons.
- Moved Clipboard and text to the right-side panel.
- Renamed clipboard actions to Paste, Type, and Copy and kept all three in one row.
- Renamed the Session card to Audio and removed the experimental badge while retaining the latency/interruption warning.
- Removed the redundant Exit focus button; Screen focus is reversed with the always-visible workspace-layout selector.
- Updated browser and release-gate regression coverage for the corrected layout.

## 0.10.1 — Optional authenticated private-LAN HTTPS access

- Kept `127.0.0.1` local-only access as the default.
- Added explicit private-interface LAN HTTPS mode with private IPv4 subnet allowlisting.
- Added generated or existing TLS certificate validation, Secure cookies, Host/Origin enforcement, and authenticated WebSocket protection.
- Added per-client login throttling metadata, network-session source information, and trust-boundary session revocation.
- Added the authenticated Network access UI, optional Windows Firewall rule management, controlled restart, public certificate download, and local-only recovery tool.


## 0.10.0 — Controlled scrcpy upstream update automation

- Added clean upstream fetch, revision selection and source-cleanliness enforcement.
- Added protocol-sensitive diff inspection with JSON and Markdown reports.
- Added isolated experimental adapter scaffolding without overwriting the stable v4.1 adapter.
- Added temporary-workspace patch application with fatal failure and automatic reset.
- Added isolated matching-server build tooling and SHA-256 build manifests.
- Added compatibility matrix generation and evidence-gated experimental/candidate/stable promotion.
- Added an offline temporary-Git Gate 10 self-test and update workflow documentation.

## 0.9.4 — Focus-mode escape and restored collapsible cards

- Moved the workspace-layout selector into the header toolbar beside Fullscreen.
- Added an explicit Exit focus button that appears whenever Screen focus layout is active.
- Restored functional collapse/expand controls for all left- and right-side cards.
- Removed the obsolete informational card titled “Controls”; this was the card intended by the earlier removal request.
- Kept every card expanded by default on each page load.
- Added accessible labels and `aria-expanded` state to each card control.
- Added browser and release-gate regression coverage for focus-mode recovery and collapsible cards.

## 0.9.3 — Two-way folder sync and status UX refinement

- Removed the non-functional card collapse controls and restored static card layouts.
- Marked browser audio as experimental with an interruption/latency warning while keeping it available.
- Added optional PC-to-Android watched-folder upload alongside Android-to-PC automatic download.
- Added stable-file detection, first-scan baselining, upload duplicate policy, verified upload queueing, and persistent counters.
- Added bidirectional fingerprints so files downloaded from Android are not uploaded back, and PC uploads are not downloaded back.
- Replaced the text/Unicode connection indicator with an animated ring status chip and removed the old pulsing Connect button state.
- Added backend, browser, API, and release-gate regression coverage for two-way sync and the new status indicator.

## 0.9.2 — Compact connection-status toolbar indicator

- Moved connection status out of the left panel and into the main connection toolbar.
- Matched the status control height to the compact connection and Android-control buttons.
- Added green connected, red disconnected and amber connecting state icons.
- Preserved detailed status text as a tooltip and screen-reader announcement.
- Corrected stream-failure ordering so the status icon changes to disconnected before reconnect handling.
- Added browser, Python and release-gate regression checks for toolbar placement and state styling.

## 0.9.1 — Collapsible side cards and compact command header

- Added a small collapse/expand button to every left- and right-side card.
- Cards are expanded by default and collapse to their header only.
- Moved Android Back, Home, Recent, Rotate, Screen off and Fullscreen controls into the connection toolbar.
- Placed the Android device selector, connection actions and Android controls on the same line as the DroidWebDisplay title on desktop widths.
- Reduced header padding and updated available viewport height for the video and transfer panels.
- Added browser regression checks for collapsible cards and the compact header layout.

## 0.9.0 — Audio, clipboard, reconnect, storage and UX completion

- Added optional Opus audio playback through browser WebCodecs and Web Audio.
- Isolated Android audio capture/configuration failures from video and control.
- Added bidirectional clipboard synchronization controls and size limits.
- Added automatic and manual reconnect flows, fullscreen shortcut and workspace layouts.
- Added settings import/export and improved keyboard focus/accessibility behavior.
- Added dynamic removable SD-card discovery under `/storage/<XXXX-XXXX>`.
- Canonicalized internal Documents paths to `/sdcard/Documents`.
- Simplified Upload, Browse, Download and Reset button labels and normalized action-row heights.
- Replaced the crosshair over the Android screen with the normal pointer cursor.
- Removed historical gate verification checkboxes from the web interface.

## 0.8.3 — Current-state repository cleanup

- Removed Phase 1–7 workflows, scripts, gate tools, historical evidence, and duplicate documentation.
- Removed the obsolete scrcpy source-build/submodule framework from the runtime release.
- Reorganized retained regression tests by feature instead of implementation phase.
- Consolidated browser evidence validation and static release checks.
- Renamed current launch and gate commands to generic `service` and `gate` entry points.
- Removed generated Python caches and runtime evidence from the distributed package.
- Preserved all current authentication, browser control, virtual display, transfer, automatic-download, and running-app features.

## 0.8.2 — Gate 8 generated-artifact correction

- Regenerated browser static hashes after connection-toolbar alignment changes.
- Regenerated OpenAPI metadata for the package version.
- Added regression coverage for left-aligned inline connection controls.

## 0.8.0 — PC-local authentication and trusted sessions

- Added first-run PIN setup, login throttling, trusted-browser durations, revocation, CSRF protection, authenticated WebSockets, audit redaction, and fail-closed local storage.
