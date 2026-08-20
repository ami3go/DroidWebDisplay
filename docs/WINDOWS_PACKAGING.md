# Windows packaging and troubleshooting

DroidWebDisplay ships Windows packages without code signing for now. The hardening in this document is independent of signing.

## Distribution forms

Future releases publish two Windows x86-64 forms from the same source commit:

- **Portable EXE** — `DroidWebDisplay-vX.Y.Z-windows-x86_64.exe`. Convenient single-file launch. PyInstaller extracts this form into a temporary runtime directory while it is running.
- **Stable onedir ZIP** — `DroidWebDisplay-vX.Y.Z-windows-x86_64.zip`. Recommended for long-running use. Extract it to a normal folder and run `DroidWebDisplay.exe`; dependencies remain in a stable directory instead of a temporary `_MEI...` extraction tree.

Both targets:

- use the same application version from `VERSION` for Windows PE FileVersion/ProductVersion metadata;
- include ProductName/FileDescription/OriginalFilename metadata;
- include a DroidWebDisplay application icon;
- bundle the verified Android platform-tools `adb.exe` and Windows ADB DLLs;
- bundle the verified scrcpy server and current web client;
- disable UPX compression to remove an unnecessary packaging/AV compatibility variable.

The portable EXE remains supported because it is useful for ad-hoc use. The onedir ZIP is the preferred form for machines where DroidWebDisplay stays open for many hours or days.

## USB and ADB troubleshooting

The Windows package contains ADB, but Windows still needs a working USB driver for the connected Android device.

Common states from `adb devices -l`:

- `unauthorized` or `authorizing` — unlock the phone and accept **Allow USB debugging?**. If the prompt does not appear, revoke USB debugging authorizations on Android, reconnect USB, and authorize again.
- `offline` — reconnect the USB cable, unlock the device, and toggle USB debugging if the state persists.
- `no permissions` / device absent — on Windows, install or update the phone manufacturer's/OEM USB driver and check Device Manager. The bundled ADB executable cannot replace a missing kernel USB driver.

The packaged application has a hidden `--adb-smoke` self-test used by CI to prove that its bundled `adb.exe` and DLLs can execute from both the portable and onedir layouts.

## Black video while controls still work

DroidWebDisplay renders H.264 in the browser through WebCodecs; it does not use scrcpy's native Windows Direct3D renderer. A black picture with working controls can therefore be browser/GPU-driver specific.

Recommended support sequence:

1. Update Chrome or Edge.
2. Update the Intel/AMD/NVIDIA display driver from the PC/GPU vendor.
3. Restart the browser and reconnect DroidWebDisplay.
4. If the picture is still black, disable browser hardware acceleration, restart the browser, and test again.
5. Record browser version, Windows version, GPU model/driver and whether disabling hardware acceleration changes the result.

This is intentionally treated as a browser/rendering diagnostic rather than as evidence that the scrcpy transport failed.

## Android 16 / scrcpy 4.1

The protected stable adapter remains scrcpy 4.1. Some Android 16 builds have reported an upstream `AbstractMethodError` involving `IDisplayWindowListener`. DroidWebDisplay now classifies that signature as `android16-display-listener-incompatibility` in virtual-display diagnostics and surfaces an Android 16 compatibility warning from the capability probe.

Do not replace the stable scrcpy adapter merely to mask this failure. A newer upstream adapter/server should be promoted only through the normal DWD compatibility, regression and hardware-in-loop gates so clipboard, control, physical display and virtual display behavior are not degraded.

## CI coverage

The Windows 2025 package gate now builds both distribution forms and verifies:

- PE ProductName, FileVersion, ProductVersion and OriginalFilename;
- bundled ADB exists and `adb version` executes;
- desktop-host smoke test;
- CLI startup;
- packaged ADB self-test;
- embedded HTTP service startup and shutdown;
- three repeated service start/stop cycles for each distribution form;
- creation of the stable onedir ZIP used by future GitHub releases.

Real USB devices, browser GPU behavior, sleep/resume and long-duration operation still require HIL testing.