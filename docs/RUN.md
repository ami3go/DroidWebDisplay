# Current release Run Guide

## Start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
.\scripts\phase8-service.ps1
```

Open `http://127.0.0.1:8765/`.

## First setup

1. Enter a 4–12 digit PIN.
2. Confirm the PIN.
3. Select a trust duration.
4. Optionally enter a browser label.
5. Press **Create PIN and unlock**.

## Login

An untrusted or expired browser sees the PIN gate before bridge APIs or WebSockets are opened.

## Revoke

Use the left-side **PC-local access** card:

- **Revoke** beside one browser.
- **Forget this browser** for the current browser.
- **Revoke all sessions** after entering the current PIN.

## Change PIN

Open **Change PIN**, enter the current PIN and the new PIN twice. Every existing browser session is revoked.

## Reset after losing the PIN

Stop the bridge:

```powershell
python tools\reset_auth.py --yes
```

Restart and create a new PIN.

## Gate

```powershell
python tools\phase8_gate.py --output .\evidence\phase8\gate8.json
```
