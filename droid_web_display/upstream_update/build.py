from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Sequence

from .git import clone_at_revision, ensure_clean
from .patches import apply_patch_series


class ServerBuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_command(workspace: Path) -> list[str]:
    if os.name == "nt":
        wrapper = workspace / "gradlew.bat"
        if not wrapper.is_file():
            raise ServerBuildError(f"Gradle wrapper is missing: {wrapper}")
        return [str(wrapper), "-p", "server", "assembleRelease"]
    wrapper = workspace / "gradlew"
    if not wrapper.is_file():
        raise ServerBuildError(f"Gradle wrapper is missing: {wrapper}")
    return [str(wrapper), "-p", "server", "assembleRelease"]


def _find_server_artifact(workspace: Path) -> Path:
    candidates: list[Path] = []
    for pattern in (
        "server/build/outputs/apk/release/*.apk",
        "server/build/outputs/apk/release/*",
        "server/build/outputs/server-*.jar",
    ):
        candidates.extend(path for path in workspace.glob(pattern) if path.is_file())
    candidates = sorted(set(candidates), key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
    if not candidates:
        raise ServerBuildError("Gradle completed but no scrcpy server artifact was found")
    return candidates[0]


def build_matching_server(
    source_repository: Path,
    *,
    revision: str,
    output: Path,
    patch_directory: Path | None = None,
    command: Sequence[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    ensure_clean(source_repository)
    output = output.resolve()
    plan = {
        "sourceRepository": str(source_repository.resolve()),
        "revision": revision,
        "output": str(output),
        "patchDirectory": str(patch_directory.resolve()) if patch_directory else None,
        "dryRun": dry_run,
    }
    if dry_run:
        return {"status": "PLANNED", **plan}
    with tempfile.TemporaryDirectory(prefix="droid-web-display-build-") as temp:
        workspace = Path(temp) / "scrcpy"
        commit = clone_at_revision(source_repository, workspace, revision)
        patches = apply_patch_series(workspace, patch_directory)
        argv = list(command) if command is not None else _default_command(workspace)
        result = subprocess.run(
            argv,
            cwd=workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=1800,
            check=False,
        )
        if result.returncode != 0:
            raise ServerBuildError(
                f"scrcpy server build failed ({result.returncode}): {(result.stderr or result.stdout)[-4000:]}"
            )
        artifact = _find_server_artifact(workspace)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact, output)
        sha = sha256_file(output)
        manifest = {
            "schemaVersion": 1,
            "builtAt": datetime.now(timezone.utc).isoformat(),
            "upstreamCommit": commit,
            "revision": revision,
            "sha256": sha,
            "bytes": output.stat().st_size,
            "artifact": str(output),
            "patchSeries": patches,
            "command": argv,
        }
        manifest_path = output.with_suffix(output.suffix + ".manifest.json")
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ensure_clean(source_repository)
    return {"status": "PASS", "manifest": str(manifest_path), **manifest}
