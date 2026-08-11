# Phase 11 packaging

`tools/build_release.py` creates a platform release tree for Windows, Linux, or a generic source bundle.

A complete offline bundle requires three externally supplied, platform-sensitive artifacts:

1. the pinned official `scrcpy-server-v4.1` (SHA-256 is verified against the compatibility manifest);
2. Android Platform-Tools (`adb`) for the target host;
3. either a bundled Python runtime or an offline wheelhouse compatible with the target host.

These are deliberately supplied to the builder rather than silently fetched during packaging. Android Platform-Tools are subject to the Android SDK License and must be acquired/accepted by the release builder. Runtime state (`data/`, TLS private keys, trusted sessions, sync history, and downloads) is never copied into release archives.

Windows build example:

```powershell
python tools\build_release.py --target windows --output dist\DroidWebDisplay-win64 `
  --scrcpy-server C:\artifacts\scrcpy-server-v4.1 `
  --adb-directory C:\artifacts\platform-tools `
  --python-runtime C:\artifacts\python-runtime `
  --require-offline-ready
```

Linux build example:

```sh
python tools/build_release.py --target linux --output dist/DroidWebDisplay-linux-x86_64 \
  --scrcpy-server /opt/artifacts/scrcpy-server-v4.1 \
  --adb-directory /opt/artifacts/platform-tools \
  --python-runtime /opt/artifacts/python-runtime \
  --require-offline-ready
```
