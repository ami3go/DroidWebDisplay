# Virtual Display Compatibility Report

## Verified device

- Manufacturer: Samsung
- Model: SM-G980F
- Android: 13 / API 33
- scrcpy server and browser adapter: 4.1

## Verified behavior

- Fixed 1600×900 virtual display at 240 DPI.
- ChatGPT launch on the virtual display.
- Browser video and control channels.
- Physical-screen fallback.
- Display cleanup after stop.
- Structured upload and download regression with SHA-256 verification.

## Compatibility handling

Samsung Android 12/13 may reject local IME routing on an untrusted virtual display. The bridge falls back to Android default IME routing while preserving browser keyboard injection.

The Samsung `app_process` stack-protector failure is avoided by omitting server arguments that equal scrcpy defaults. Non-default virtual-display options remain supported.

## Remaining release validation

Long-run stability, repeated flex resizing, and device-specific application relocation should be repeated when Android firmware, scrcpy, encoder, or browser versions change.
