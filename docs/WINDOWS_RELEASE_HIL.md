# Windows release HIL checklist

Run this checklist on the exact packaged Windows artifact before promoting a release when hardware is available. CI covers package startup, repeated shutdown, bundled ADB execution, PE version metadata and service availability; the checks below qualify the real Windows + browser + Android path.

- Start both the portable EXE and extracted stable onedir ZIP.
- Verify an unauthorized phone is reported by ADB and becomes ready after accepting **Allow USB debugging?**.
- Connect physical display and confirm the first video frame appears without requiring Rotate.
- Rotate twice and confirm video remains/reconnects correctly.
- Verify mouse/touch controls, PC keyboard input, Back/Home/Recent and display power control.
- Verify Android → PC automatic clipboard, Copy button and Ctrl+C.
- Verify PC → Android automatic clipboard, Paste/Ctrl+V and Type; normal PC typing must remain usable.
- Disconnect/reconnect and confirm clipboard/session state does not leak between sessions.
- Transfer a file Android → PC and PC → Android.
- Leave a session active through Windows display-off and sleep/resume, then verify service, video and control recovery.
- Run a multi-hour soak and confirm no orphan `DroidWebDisplay.exe`, `adb.exe`, server process, occupied service port or unexpected `_MEI...` directory remains after exit.
- On at least one Android 16 device, confirm normal operation or capture the explicit `android16-display-listener-incompatibility` classification when the upstream scrcpy signature occurs.
- For any black-video report with working controls, record Chrome/Edge version, GPU and driver version, and the result of disabling browser hardware acceleration.

A release must not claim this HIL coverage unless it was actually performed on the packaged artifact.