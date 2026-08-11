# Gpt-Bridge scrcpy

Browser control of an Android phone with physical and virtual displays, structured file transfer, two-way watched-folder transfer, running-app relocation, and PIN-protected trusted browser sessions, with optional authenticated private-LAN HTTPS access.

## Current baseline

- Gpt-Bridge: `0.11.2`
- scrcpy server and browser protocol adapter: `4.1`
- Default service: `http://127.0.0.1:8765/`
- Optional LAN mode: explicit private-interface HTTPS with client-subnet allowlisting
- Trust authority: the local PC bridge service, not the Android phone
- Automatic-download and virtual-display HIL: PASS on Samsung SM-G980F

## Windows installation

Copy the verified `scrcpy-server-v4.1` into `server\`, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
.\scripts\service.ps1
```

Open `http://127.0.0.1:8765/`.

The official pinned server can also be downloaded and hash-verified with:

```powershell
python tools\download_server.py
```

## Release gate

```powershell
python tools\release_gate.py --output .\evidence\release\gate.json
```

Or:

```powershell
.\scripts\gate.ps1
```

Optional browser evidence:

```powershell
python tools\release_gate.py `
  --require-browser-evidence `
  --browser-evidence .\evidence\release\browser.json `
  --output .\evidence\release\gate-complete.json
```

## Authentication and recovery

The local service provides first-run PIN setup, trusted-browser expiration, individual and global revocation, CSRF protection, and authenticated WebSockets. The Android phone is not the trust authority.

To reset a lost PIN, stop the service and run:

```powershell
python tools\reset_auth.py --yes
```

## Optional private-LAN access

LAN access is disabled by default. After local authentication, use the **Network access** card to select a private interface, generate or validate a TLS certificate, define allowed client subnets, and restart the service. All trusted sessions are revoked when the trust boundary changes.

Emergency recovery:

```powershell
python tools\reset_network_access.py --local-only
```

See `docs/NETWORK_ACCESS.md`.

## Documentation

- `docs/ARCHITECTURE.md`
- `docs/RUN.md`
- `docs/SECURITY_REVIEW.md`
- `docs/GATE_REVIEW.md`
- `docs/VIRTUAL_DISPLAY.md`
- `docs/VIRTUAL_DISPLAY_TROUBLESHOOTING.md`
- `docs/TWO_WAY_FOLDER_SYNC.md`
- `docs/CLEANUP_REPORT.md`
- `docs/UPSTREAM_UPDATE.md`
- `docs/NETWORK_ACCESS.md`


## Controlled scrcpy updates

Phase 10 adds an isolated update workflow that keeps the approved v4.1 adapter available while a target upstream revision is inspected, scaffolded, built and evidence-qualified. Start with:

```powershell
python tools\update_scrcpy.py --target <tag-or-commit> --version <version> --clone-if-missing --fetch --scaffold-adapter --register
```

See `docs/UPSTREAM_UPDATE.md` for inspection, patch, build and promotion commands.

## Phase 11 packaging

Platform release trees are built with `tools/build_release.py`. The builder supports Windows, Linux, and generic source targets, verifies the pinned scrcpy server SHA-256, generates `VERSION.json`, installs license files, excludes runtime secrets, and supports optional bundled adb/Python/wheelhouse inputs.

A fully offline bundle requires target-platform artifacts supplied at build time: the verified scrcpy server, an accepted Android Platform-Tools directory, and either a bundled Python runtime or an offline wheelhouse. See `packaging/README.md`.
