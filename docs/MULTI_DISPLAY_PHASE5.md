# Multi-display Phase 5 — Hardening and Qualification

Phase 5 hardens the Phase 1–4 multi-display implementation without changing the scrcpy v4.1 media/control protocol.

## Runtime limits

- Default maximum simultaneous display sessions per Android device: **4**.
- Configurable range: **1..8** through `BridgeConfig.maximum_display_sessions`.
- Capacity is reserved atomically before a new scrcpy transport is allocated.
- Capacity is independent per Android serial.
- Stopping or failing one display releases only that display's slot.

The device-scoped sessions API reports `maximumSessions` and `availableSlots`. The browser disables Connect / New display when no slot remains.

## Instant tab switching

The tab-switch path is browser-local and has a qualification target of **less than 50 ms**. Switching a live tab changes the active runtime/canvas and input/audio routing only. It does not start a session, query ADB, recreate a virtual display, launch an application, or restart scrcpy.

The Diagnostics drawer reports the most recent browser tab-switch duration and per-display video/audio state. Server-side display diagnostics are available at:

```text
GET /api/v1/devices/{serial}/display-diagnostics
```

## Automated qualification

The normal release gate covers:

- default/range capacity validation;
- fifth-session rejection at the default limit;
- capacity release after normal stop and isolated server failure;
- independent capacity across Android devices;
- HTTP 409 conflict response when capacity is exhausted;
- per-display diagnostic response;
- browser-only tab-switch source contract;
- visible browser capacity and per-display diagnostics;
- all pre-existing session, browser, protocol, transfer, auth and packaging regressions.

## Hardware qualification

Before merging, exercise the feature on the target Android device:

1. Run four simultaneous displays (physical/virtual mix supported by the device).
2. Switch repeatedly between every tab and confirm immediate video/input focus changes.
3. Confirm only the active tab produces audible audio.
4. Close each tab in a different order and verify the other sessions continue.
5. Force one session failure (USB/server interruption where practical) and verify sibling lifecycle isolation.
6. Start a replacement display after a slot is released.
7. Keep file transfer active while switching tabs and confirm screen control remains responsive.
8. Record Diagnostics output and the observed tab-switch responsiveness.

Hardware-specific latency cannot be certified by GitHub Actions; the automated gate qualifies the architecture and deterministic lifecycle behavior.
