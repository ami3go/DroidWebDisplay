from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any, Iterable

from droid_web_display import __version__


class PackagingError(RuntimeError):
    pass


RUNTIME_COPY_PATHS = (
    "droid_web_display",
    "apps/web-client/dist",
    "apps/web-client/dist-manifest.json",
    "packages/scrcpy-protocol/dist",
    "packages/scrcpy-protocol/package.json",
    "compatibility/scrcpy-versions.json",
    "patches/scrcpy",
    "tools/run_bridge_service.py",
    "tools/stop_bridge_service.py",
    "tools/reset_auth.py",
    "tools/reset_network_access.py",
    "tools/migrate_config.py",
    "pyproject.toml",
    "requirements-lock.txt",
    "requirements-runtime.txt",
)

STATE_FILES = (
    "auth.json",
    "network-access.json",
    "auto-download-monitor.json",
)




def _build_timestamp() -> str:
    """Return a reproducible release timestamp when SOURCE_DATE_EPOCH is set.

    The default is the Unix epoch so two packaging runs over the same tree do not
    differ only because of wall-clock time. Release CI may set SOURCE_DATE_EPOCH
    to the source commit timestamp.
    """
    raw = os.environ.get("SOURCE_DATE_EPOCH", "0")
    try:
        epoch = int(raw)
    except ValueError as exc:
        raise PackagingError("SOURCE_DATE_EPOCH must be an integer Unix timestamp") from exc
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_clean(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise PackagingError(f"refusing to package symlink: {source}")
    if source.is_dir():
        shutil.copytree(
            source,
            destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "node_modules"),
        )
    elif source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    else:
        raise PackagingError(f"required runtime path is missing: {source}")


def _safe_state_source(previous_root: Path, relative: Path) -> Path:
    source = (previous_root / "data" / relative).resolve()
    data_root = (previous_root / "data").resolve()
    try:
        source.relative_to(data_root)
    except ValueError as exc:
        raise PackagingError(f"state path escapes previous data directory: {relative}") from exc
    return source


def migrate_runtime_state(previous_root: Path, new_root: Path) -> dict[str, Any]:
    previous_root = previous_root.resolve()
    new_root = new_root.resolve()
    copied: list[str] = []
    skipped: list[str] = []
    destination_data = new_root / "data"
    destination_data.mkdir(parents=True, exist_ok=True)

    for name in STATE_FILES:
        relative = Path(name)
        source = _safe_state_source(previous_root, relative)
        destination = destination_data / relative
        if not source.is_file():
            skipped.append(name)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".migrate")
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
        copied.append(name)

    tls_source = _safe_state_source(previous_root, Path("tls"))
    if tls_source.is_dir():
        tls_destination = destination_data / "tls"
        tls_destination.mkdir(parents=True, exist_ok=True)
        for source in sorted(tls_source.iterdir()):
            if source.is_symlink() or not source.is_file() or source.suffix.lower() not in {".pem", ".crt", ".key"}:
                continue
            destination = tls_destination / source.name
            shutil.copy2(source, destination)
            copied.append(f"tls/{source.name}")

    return {"schemaVersion": 1, "copied": copied, "skipped": skipped}


@dataclass(frozen=True)
class ReleaseInputs:
    target: str
    scrcpy_server: Path | None = None
    adb_directory: Path | None = None
    python_runtime: Path | None = None
    wheelhouse: Path | None = None
    allow_missing_server: bool = False


def _compatibility(root: Path) -> tuple[str, dict[str, Any]]:
    payload = json.loads((root / "compatibility/scrcpy-versions.json").read_text(encoding="utf-8"))
    adapter = str(payload["defaultAdapter"])
    entry = payload["supportedVersions"][adapter]
    return adapter, entry


def _copy_server(root: Path, release: Path, inputs: ReleaseInputs) -> dict[str, Any]:
    adapter, entry = _compatibility(root)
    version = str(entry["version"])
    expected_sha = str(entry.get("serverSha256") or entry["officialReleaseServerSha256"]).lower()
    source = inputs.scrcpy_server
    if source is None:
        candidates = (root / "server" / f"scrcpy-server-v{version}", root / "server" / "scrcpy-server")
        source = next((candidate for candidate in candidates if candidate.is_file()), None)
    server_dir = release / "server"
    server_dir.mkdir(parents=True, exist_ok=True)
    if source is None:
        if not inputs.allow_missing_server:
            raise PackagingError(
                f"verified scrcpy server v{version} is required; provide --scrcpy-server or place it in server/"
            )
        manifest = {
            "schemaVersion": 1,
            "present": False,
            "scrcpyVersion": version,
            "adapter": adapter,
            "expectedSha256": expected_sha,
            "serverProvenance": entry.get("serverProvenance", "official-release"),
            "patchSeries": entry.get("patchSeries", []),
            "officialBaseReleaseUrl": entry.get("officialReleaseServerUrl"),
        }
        (server_dir / "scrcpy-server.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return manifest

    source = source.resolve()
    actual_sha = sha256_file(source)
    if actual_sha != expected_sha:
        raise PackagingError(f"scrcpy server SHA-256 mismatch: {actual_sha}; expected {expected_sha}")
    destination = server_dir / f"scrcpy-server-v{version}"
    shutil.copy2(source, destination)
    manifest = {
        "schemaVersion": 1,
        "present": True,
        "scrcpyVersion": version,
        "adapter": adapter,
        "upstreamCommit": entry.get("upstreamCommit"),
        "sha256": actual_sha,
        "serverProvenance": entry.get("serverProvenance", "official-release"),
        "patchSeries": entry.get("patchSeries", []),
        "officialBaseReleaseUrl": entry.get("officialReleaseServerUrl"),
    }
    (server_dir / "scrcpy-server.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _copy_optional_directory(source: Path | None, destination: Path) -> bool:
    if source is None:
        return False
    source = source.resolve()
    if not source.is_dir():
        raise PackagingError(f"optional directory does not exist: {source}")
    _copy_clean(source, destination)
    return True


def _launcher_texts(target: str) -> dict[str, str]:
    windows_ps1 = r'''$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = Join-Path $Root "runtime\python\python.exe" }
if (-not (Test-Path $Python)) { $Python = Join-Path $Root "runtime\python\Scripts\python.exe" }
if (-not (Test-Path $Python)) { $Python = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $Python) { throw "Python 3.11+ is required. Run install.ps1 with an offline wheelhouse/runtime bundle." }
$Adb = Join-Path $Root "adb\adb.exe"
if (-not (Test-Path $Adb)) { $Adb = "adb" }
& $Python (Join-Path $Root "tools\run_bridge_service.py") --repo-root $Root --adb $Adb --open-browser @args
exit $LASTEXITCODE
'''
    windows_cmd = r'''@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0DroidWebDisplay.ps1" %*
exit /b %ERRORLEVEL%
'''
    linux_sh = r'''#!/usr/bin/env sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON="$ROOT/.venv/bin/python3"
if [ ! -x "$PYTHON" ]; then PYTHON="$ROOT/runtime/python/bin/python3"; fi
if [ ! -x "$PYTHON" ]; then PYTHON=$(command -v python3 || true); fi
if [ -z "${PYTHON:-}" ]; then echo "Python 3.11+ is required." >&2; exit 2; fi
ADB="$ROOT/adb/adb"
if [ ! -x "$ADB" ]; then ADB=$(command -v adb || true); fi
if [ -z "${ADB:-}" ]; then echo "adb is required. Install Android Platform-Tools or bundle adb/." >&2; exit 2; fi
exec "$PYTHON" "$ROOT/tools/run_bridge_service.py" --repo-root "$ROOT" --adb "$ADB" --open-browser "$@"
'''
    if target == "windows":
        return {"DroidWebDisplay.ps1": windows_ps1, "DroidWebDisplay.cmd": windows_cmd}
    if target == "linux":
        return {"DroidWebDisplay.sh": linux_sh}
    return {"DroidWebDisplay.ps1": windows_ps1, "DroidWebDisplay.cmd": windows_cmd, "DroidWebDisplay.sh": linux_sh}


def _runtime_dependencies(root: Path) -> list[str]:
    path = root / "requirements-runtime.txt"
    dependencies: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        dependencies.append(line)
    return dependencies


def _adb_revision(adb_directory: Path | None) -> str | None:
    if adb_directory is None:
        return None
    properties = adb_directory / "source.properties"
    if not properties.is_file():
        return None
    for line in properties.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Pkg.Revision") and "=" in line:
            return line.split("=", 1)[1].strip()
    return None


def build_release_tree(root: Path, output: Path, inputs: ReleaseInputs) -> dict[str, Any]:
    root = root.resolve()
    output = output.resolve()
    if inputs.target not in {"windows", "linux", "source"}:
        raise PackagingError("target must be windows, linux, or source")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for relative in RUNTIME_COPY_PATHS:
        _copy_clean(root / relative, output / relative)

    # Runtime directories are intentionally empty in a new package.
    for directory in ("config", "data", "downloads", "logs"):
        (output / directory).mkdir(parents=True, exist_ok=True)

    server_manifest = _copy_server(root, output, inputs)
    adb_bundled = _copy_optional_directory(inputs.adb_directory, output / "adb")
    runtime_bundled = _copy_optional_directory(inputs.python_runtime, output / "runtime/python")
    wheelhouse_bundled = _copy_optional_directory(inputs.wheelhouse, output / "wheelhouse")

    licenses = output / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "LICENSE", licenses / "DroidWebDisplay-LICENSE.txt")
    # scrcpy 4.1 is Apache-2.0; package the complete license text with an explicit name.
    shutil.copy2(root / "LICENSE", licenses / "scrcpy-LICENSE.txt")
    shutil.copy2(root / "THIRD_PARTY_NOTICES.md", licenses / "THIRD_PARTY_NOTICES.txt")

    for name, text in _launcher_texts(inputs.target).items():
        path = output / name
        path.write_text(text, encoding="utf-8", newline="\n")
        if path.suffix == ".sh":
            path.chmod(0o755)

    platform_packaging = root / "packaging" / inputs.target
    if platform_packaging.is_dir():
        _copy_clean(platform_packaging, output / "packaging" / inputs.target)

    adapter, entry = _compatibility(root)
    web_manifest = root / "apps/web-client/dist-manifest.json"
    protocol_package = root / "packages/scrcpy-protocol/package.json"
    version_manifest = {
        "schemaVersion": 1,
        "application": {"name": "DroidWebDisplay", "version": __version__},
        "target": inputs.target,
        "generatedAt": _build_timestamp(),
        "scrcpy": {
            "adapter": adapter,
            "version": entry.get("version"),
            "upstreamCommit": entry.get("upstreamCommit"),
            "server": server_manifest,
        },
        "webClientManifestSha256": sha256_file(web_manifest),
        "protocolPackageSha256": sha256_file(protocol_package),
        "python": {
            "minimum": "3.11",
            "runtimeBundled": runtime_bundled,
            "offlineWheelhouseBundled": wheelhouse_bundled,
            "runtimeDependencies": _runtime_dependencies(root),
        },
        "adb": {"bundled": adb_bundled, "revision": _adb_revision(inputs.adb_directory)},
        "networkDefault": "local-only",
        "configurationMigrationSchema": 1,
    }
    (output / "VERSION.json").write_text(json.dumps(version_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ready = bool(server_manifest.get("present")) and (runtime_bundled or wheelhouse_bundled) and adb_bundled
    readme = f"""DroidWebDisplay {__version__}\n\nTarget: {inputs.target}\nOffline-ready bundle: {'yes' if ready else 'no'}\n\nRun the platform launcher in this directory.\nLocal-only access remains the default at http://127.0.0.1:8765/.\n\nIf this package does not bundle Python, adb, or the verified scrcpy server, use the installer/build tooling to provide them before deployment.\nConfiguration and authentication state are stored under data/ and are not shipped in release archives.\n"""
    (output / "README.txt").write_text(readme, encoding="utf-8")

    package_manifest = {
        "schemaVersion": 1,
        "applicationVersion": __version__,
        "target": inputs.target,
        "generatedAt": _build_timestamp(),
        "files": inventory_tree(output),
    }
    (output / "PACKAGE-MANIFEST.json").write_text(
        json.dumps(package_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    return {
        "root": str(output),
        "readyForOfflineUse": ready,
        "manifest": version_manifest,
        "packageManifest": str(output / "PACKAGE-MANIFEST.json"),
    }


def inventory_tree(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        records.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    return records


def validate_release_tree(root: Path, *, require_offline_ready: bool = False) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    required = [
        "VERSION.json", "PACKAGE-MANIFEST.json", "README.txt", "droid_web_display", "apps/web-client/dist/index.html",
        "compatibility/scrcpy-versions.json", "server/scrcpy-server.manifest.json",
        "licenses/DroidWebDisplay-LICENSE.txt", "licenses/scrcpy-LICENSE.txt", "licenses/THIRD_PARTY_NOTICES.txt",
    ]
    for relative in required:
        if not (root / relative).exists():
            errors.append(f"missing: {relative}")
    for forbidden in ("auth.json", "network-access.json", "auto-download-monitor.json"):
        if list(root.rglob(forbidden)):
            errors.append(f"runtime state leaked into package: {forbidden}")
    if list(root.rglob("*.key")):
        errors.append("private key leaked into release package")
    try:
        manifest = json.loads((root / "VERSION.json").read_text(encoding="utf-8"))
        if manifest.get("application", {}).get("version") != __version__:
            errors.append("VERSION.json application version mismatch")
        if require_offline_ready:
            server_present = manifest.get("scrcpy", {}).get("server", {}).get("present") is True
            python_ready = manifest.get("python", {}).get("runtimeBundled") or manifest.get("python", {}).get("offlineWheelhouseBundled")
            adb_ready = manifest.get("adb", {}).get("bundled") is True
            if not (server_present and python_ready and adb_ready):
                errors.append("package is not a complete offline runtime bundle")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid VERSION.json: {exc}")

    try:
        package_manifest = json.loads((root / "PACKAGE-MANIFEST.json").read_text(encoding="utf-8"))
        listed = package_manifest.get("files", [])
        for record in listed:
            relative = str(record.get("path", ""))
            path = root / relative
            if not path.is_file():
                errors.append(f"package manifest missing file: {relative}")
                continue
            if path.stat().st_size != int(record.get("bytes", -1)):
                errors.append(f"package manifest size mismatch: {relative}")
            if sha256_file(path) != str(record.get("sha256", "")):
                errors.append(f"package manifest checksum mismatch: {relative}")
        expected_paths = {item["path"] for item in inventory_tree(root) if item["path"] != "PACKAGE-MANIFEST.json"}
        listed_paths = {str(item.get("path")) for item in listed}
        if expected_paths != listed_paths:
            errors.append("PACKAGE-MANIFEST.json file inventory mismatch")
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        errors.append(f"invalid PACKAGE-MANIFEST.json: {exc}")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors, "files": len(inventory_tree(root))}
