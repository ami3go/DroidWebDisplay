# DroidWebDisplay Run Guide

## Recommended: run a packaged release

Normal users should run a packaged GitHub Release rather than install the development toolchain.

Release downloads:

https://github.com/ami3go/DroidWebDisplay/releases

Always download the platform binary and `SHA256SUMS.txt` from the same release and verify the checksum before running it.

### Windows x86_64

Run the downloaded executable:

```powershell
.\DroidWebDisplay-*-windows-x86_64.exe
```

The executable starts the local service and opens the browser UI automatically. Keep the process running while using DroidWebDisplay.

State locations:

- application state: `%LOCALAPPDATA%\DroidWebDisplay`
- default downloads: `%USERPROFILE%\Downloads\DroidWebDisplay`

### Linux x86_64

```bash
chmod +x DroidWebDisplay-*-linux-x86_64.AppImage
./DroidWebDisplay-*-linux-x86_64.AppImage
```

If FUSE/AppImage integration is unavailable:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 ./DroidWebDisplay-*-linux-x86_64.AppImage
```

State locations:

- application state: `${XDG_STATE_HOME:-$HOME/.local/state}/droidwebdisplay`
- default downloads: `$HOME/Downloads/DroidWebDisplay`

The default local URL is `http://127.0.0.1:8765/`.

## First setup

1. Enable Android **Developer options** and **USB debugging**.
2. Connect the Android device and accept the Android debugging authorization prompt if shown.
3. Start DroidWebDisplay.
4. Enter a 4–12 digit PIN.
5. Confirm the PIN.
6. Select a trust duration.
7. Optionally enter a browser label.
8. Press **Create PIN and unlock**.

## Login

An untrusted or expired browser sees the PIN gate before bridge APIs or WebSockets are opened.

## Revoke trusted browsers

Use the **Access** drawer:

- **Revoke** beside one browser.
- **Forget this browser** for the current browser.
- **Revoke all trusted sessions** after entering the current PIN.

## Change PIN

Open **Change PIN**, enter the current PIN and the new PIN twice. Every existing browser session is revoked.

## Source/development run

For development, install Python 3.11, Node.js 22, and uv. From the repository root:

### Windows

```powershell
uv python install 3.11
uv sync --locked --extra dev
uv run python tools\download_server.py
.\scripts\service.ps1
```

### Linux

```bash
uv python install 3.11
uv sync --locked --extra dev
uv run python tools/download_server.py
./scripts/service.sh
```

Open `http://127.0.0.1:8765/` if the browser does not open automatically.

## Reset after losing the PIN

The repository source checkout includes the administrative reset helper. Stop DroidWebDisplay, then run:

```powershell
uv run python tools\reset_auth.py --yes
```

Restart the service and create a new PIN.

Packaged releases currently do not expose `reset_auth.py` as a separate executable. The persistent state locations above are therefore important for backup/troubleshooting and for future packaged recovery tooling.

## Current release gate

Maintainers should use the complete release gate rather than historical phase-specific gates:

```powershell
uv run python tools\release_gate.py --output .\evidence\release\gate.json
```

Or on Windows:

```powershell
.\scripts\gate.ps1
```
