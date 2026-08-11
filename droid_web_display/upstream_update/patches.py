from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from .git import GitCommandError, ensure_clean, run_git


class PatchApplicationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PatchRecord:
    path: str
    sha256: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_patch_series(directory: Path | None) -> list[Path]:
    if directory is None:
        return []
    if not directory.is_dir():
        raise PatchApplicationError(f"patch directory does not exist: {directory}")
    return sorted(path for path in directory.iterdir() if path.is_file() and path.suffix == ".patch")


def apply_patch_series(workspace: Path, patch_directory: Path | None) -> list[dict[str, Any]]:
    ensure_clean(workspace)
    patches = discover_patch_series(patch_directory)
    records: list[dict[str, Any]] = []
    try:
        for patch in patches:
            run_git(workspace, ["apply", "--check", "--whitespace=error-all", str(patch)])
            run_git(workspace, ["apply", "--whitespace=error-all", str(patch)])
            records.append({"path": str(patch.resolve()), "sha256": _sha256(patch)})
    except GitCommandError as exc:
        run_git(workspace, ["reset", "--hard", "HEAD"], check=False)
        run_git(workspace, ["clean", "-fdx"], check=False)
        raise PatchApplicationError(f"patch series stopped and workspace was reset: {exc}") from exc
    return records
