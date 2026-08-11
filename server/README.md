# Pinned scrcpy server

The bridge loads the Android server artifact only when a screen-control session is created. Health, authentication, device discovery, and file APIs can start before the artifact is present.

Download and verify the pinned official server:

```powershell
python tools\download_server.py
```

Expected artifact:

```text
server/scrcpy-server-v4.1
```

The service validates its SHA-256 and compatibility metadata against `compatibility/scrcpy-versions.json`.
