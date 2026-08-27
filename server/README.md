# Pinned compatible scrcpy server

The bridge loads the Android server artifact when a screen-control session is created or when it asks Android's PackageManager for localized application labels. Health, authentication, device discovery, and file APIs can start before the artifact is present; application discovery retains a package-name fallback when the artifact is unavailable.

The repository tracks the verified v4.1 server used at runtime. Verify it with:

```powershell
python tools\download_server.py
```

Expected artifact:

```text
server/scrcpy-server-v4.1
```

This binary is built from the pinned upstream v4.1 commit plus the deterministic
manual-clipboard patch in `patches/scrcpy/`. Native clipboard autosync remains
enabled. The service validates the server SHA-256 and compatibility metadata
against `compatibility/scrcpy-versions.json`; the manifest also pins the patch
SHA-256.
