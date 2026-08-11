# Virtual Display Troubleshooting

## Virtual mode is disabled

Confirm Android API is at least 29, the device is authorized, and the bundled server is exactly v4.1. Use Physical Screen mode when the device cannot create or control a secondary display.

## ChatGPT is not listed

Refresh installed applications and confirm `com.openai.chatgpt` is installed on the connected phone. The bridge does not install or update Android applications.

## Display is created but blank

Enable system decorations, use the ChatGPT Desktop profile, and verify the selected package launches on secondary displays. Some applications reject secondary-display launch.

## Encoder fails

Use H.264 and the Low Bandwidth profile. Reduce resolution, bitrate, or FPS.

## Input is offset after resizing

Wait for the resizing indicator to clear and for the new video dimensions to appear. Avoid browser zoom during diagnosis. Clicking outside the rendered video content should inject no event.

## On-screen keyboard appears on the phone

Try IME policy `local`. Device/vendor behavior may still route the IME to the physical display. Browser keyboard injection and clipboard fallback remain available.

## Display remains after an abnormal stop

Reconnect USB, restart the bridge, and start/stop a new Physical or Virtual session. The startup and shutdown paths record display cleanup evidence. A phone reboot clears Android display state if vendor software left a stale display.

## Samsung Android 12/13 local IME policy

Some Samsung Android 12/13 builds reject `display_ime_policy=local` for an untrusted virtual display.
The compatibility probe detects this combination and uses Android default IME routing while preserving browser keyboard injection.
The session diagnostics record both the requested and effective IME policies.

## Diagnostic HIL first

Run one cycle before a ten-cycle release gate:

```powershell
Run the current release gate and capture browser diagnostics from the virtual-display session. Historical standalone virtual-display HIL tooling was removed during repository cleanup.
```

On failure, inspect `details.classification`, `details.serverArguments`, `details.serverLog`, and `details.displayStateTail`.


## `stack corruption detected (-fstack-protector)`

Some Samsung Android builds have an `app_process` compatibility defect that may abort when the scrcpy server is launched with an unnecessarily long argument vector.

Gpt-Bridge v0.6.2 follows the native scrcpy v4.1 client and omits options that equal server defaults. For the recommended Samsung profile this reduces the server list from 14 entries to 9 while preserving the requested 1600×900/240 display, bitrate, frame rate, tunnel, and keep-active behavior.

Evidence classification:

```text
app-process-stack-corruption
```

Do not lower the resolution merely to address this message; it is an argument-launch failure, not an encoder-capacity failure. Verify that the report does not include redundant values such as:

```text
cleanup=true
video_codec=h264
max_size=0
flex_display=false
vd_system_decorations=true
vd_destroy_content=true
```


## Prevent the Android keyboard from opening on the phone

When using a virtual display, enable **Hide Android on-screen keyboard on virtual display** in Display mode settings. The bridge maps this to scrcpy `display_ime_policy=hide`. The option is emitted only for virtual-display sessions; physical Phone screen mode is not changed.
