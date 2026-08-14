# DroidWebDisplay

Browser control of an Android phone with physical and virtual displays, structured file transfer, two-way watched-folder transfer, running-app relocation, and PIN-protected trusted browser sessions, with optional authenticated private-LAN HTTPS access.

## Current baseline

- DroidWebDisplay: `0.11.2`
- scrcpy server and browser protocol adapter: `4.1`
- Default service: `http://127.0.0.1:8765/`
- Optional LAN mode: explicit private-interface HTTPS with client-subnet allowlisting
- Trust authority: the local PC bridge service, not the Android phone
- Automatic-download and virtual-display HIL: PASS on Samsung SM-G980F

## Install a release build

For normal use, install a packaged release build. The Windows executable and Linux AppImage are self-contained; Python, Node.js, npm, and uv are not required on the target PC.

Download releases from:

https://github.com/ami3go/DroidWebDisplay/releases

During release-candidate qualification, published builds may be marked **Pre-release**. Check the release notes for the exact source commit, signing status, and any validation limitations. Use `SHA256SUMS.txt` from the same release to verify the downloaded binary.

### Windows x86_64

1. Download the matching `DroidWebDisplay-...-windows-x86_64.exe` and `SHA256SUMS.txt` from the same GitHub Release.
2. Resolve the downloaded executable and verify its hash in PowerShell:

```powershell
$exe = Get-ChildItem .\DroidWebDisplay-*-windows-x86_64.exe | Select-Object -First 1
if (-not $exe) { throw "DroidWebDisplay Windows executable not found" }
Get-FileHash $exe.FullName -Algorithm SHA256
Get-Content .\SHA256SUMS.txt
```

Confirm that the SHA-256 shown by `Get-FileHash` matches the line for the executable in `SHA256SUMS.txt`.

3. Start the executable:

```powershell
& $exe.FullName
```

DroidWebDisplay starts the local bridge service and opens the browser interface automatically. Keep the DroidWebDisplay process running while using the browser UI.

Local state is stored under `%LOCALAPPDATA%\DroidWebDisplay`. Browser downloads default to `%USERPROFILE%\Downloads\DroidWebDisplay`.

If Windows reports an unknown publisher for an unsigned pre-release, verify the release notes and SHA-256 checksum before deciding whether to run it. Do not bypass a checksum mismatch.

### Linux x86_64

1. Download the matching `DroidWebDisplay-...-linux-x86_64.AppImage` and `SHA256SUMS.txt` from the same GitHub Release.
2. Verify the AppImage:

```bash
sha256sum -c SHA256SUMS.txt --ignore-missing
```

3. Make it executable and start it:

```bash
chmod +x DroidWebDisplay-*-linux-x86_64.AppImage
./DroidWebDisplay-*-linux-x86_64.AppImage
```

DroidWebDisplay starts the local bridge service and opens the browser interface automatically. If AppImage/FUSE integration is unavailable on the host, use the extraction fallback:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 ./DroidWebDisplay-*-linux-x86_64.AppImage
```

Local state is stored under `${XDG_STATE_HOME:-$HOME/.local/state}/droidwebdisplay`. Browser downloads default to `$HOME/Downloads/DroidWebDisplay`.

## First run

1. Enable Android **Developer options** and **USB debugging**.
2. Connect the Android device over USB and accept the Android debugging authorization prompt if shown.
3. Start DroidWebDisplay. The packaged application includes its required desktop runtime components and launches the local web UI.
4. Create a 4–12 digit DroidWebDisplay PIN and choose the browser trust duration.
5. Use the browser UI to open the physical display or create a virtual display.

The default service listens only on the local PC at `http://127.0.0.1:8765/`.

## Authentication and recovery

The local service provides first-run PIN setup, trusted-browser expiration, individual and global revocation, CSRF protection, and authenticated WebSockets. The Android phone is not the trust authority.

For a source checkout, a lost PIN can be reset after stopping the service:

```powershell
uv run python tools\reset_auth.py --yes
```

See `docs/RUN.md` for packaged-build state locations and source-run details.

## Optional private-LAN access

LAN access is disabled by default. After local authentication, use the **Network access** card to select a private interface, generate or validate a TLS certificate, define allowed client subnets, and restart the service. All trusted sessions are revoked when the trust boundary changes.

For a source checkout, emergency local-only network recovery is available with:

```powershell
uv run python tools\reset_network_access.py --local-only
```

See `docs/NETWORK_ACCESS.md`.

## Development from source

The source workflow is for development and release work, not the normal end-user installation path.

Prerequisites:

- Python 3.11
- Node.js 22
- uv

Install uv using the official uv installation instructions, then from the repository root run:

### Windows

```powershell
uv python install 3.11
uv sync --locked --extra dev
uv run python tools\download_server.py
.\scripts\service.ps1
```

### Linux / Ubuntu

```bash
uv python install 3.11
uv sync --locked --extra dev
uv run python tools/download_server.py
./scripts/service.sh
```

Open `http://127.0.0.1:8765/` if the browser does not open automatically.

## Release gate

Maintainers can run the current release gate with:

```powershell
uv run python tools\release_gate.py --output .\evidence\release\gate.json
```

Or on Windows:

```powershell
.\scripts\gate.ps1
```

Optional browser evidence:

```powershell
uv run python tools\release_gate.py `
  --require-browser-evidence `
  --browser-evidence .\evidence\release\browser.json `
  --output .\evidence\release\gate-complete.json
```

## Documentation

- `docs/RUN.md`
- `docs/ARCHITECTURE.md`
- `docs/SECURITY_REVIEW.md`
- `docs/GATE_REVIEW.md`
- `docs/VIRTUAL_DISPLAY.md`
- `docs/VIRTUAL_DISPLAY_TROUBLESHOOTING.md`
- `docs/TWO_WAY_FOLDER_SYNC.md`
- `docs/CLEANUP_REPORT.md`
- `docs/UPSTREAM_UPDATE.md`
- `docs/NETWORK_ACCESS.md`
- `SECURITY.md`

## Controlled scrcpy updates

The isolated upstream-update workflow keeps the approved v4.1 adapter available while a target upstream revision is inspected, scaffolded, built, and evidence-qualified. Start with:

```powershell
uv run python tools\update_scrcpy.py --target <tag-or-commit> --version <version> --clone-if-missing --fetch --scaffold-adapter --register
```

See `docs/UPSTREAM_UPDATE.md` for inspection, patch, build, and promotion commands.

## Packaging internals

Platform release trees are built with `tools/build_release.py`. The builder supports Windows, Linux, and generic source targets, verifies the pinned scrcpy server SHA-256, generates `VERSION.json`, installs license files, excludes runtime secrets, and supports optional bundled adb/Python/wheelhouse inputs.

A fully offline source-built bundle requires target-platform artifacts supplied at build time: the verified scrcpy server, an accepted Android Platform-Tools directory, and either a bundled Python runtime or an offline wheelhouse. See `packaging/README.md`.
