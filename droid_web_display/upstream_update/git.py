from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Iterable


class GitCommandError(RuntimeError):
    """Raised when a required git operation fails."""


@dataclass(frozen=True)
class GitResult:
    argv: tuple[str, ...]
    stdout: str
    stderr: str
    returncode: int


def git_executable() -> str:
    executable = shutil.which("git")
    if not executable:
        raise GitCommandError("git executable is not available")
    return executable


def run_git(
    repository: Path | None,
    arguments: Iterable[str],
    *,
    check: bool = True,
    timeout: float = 180.0,
) -> GitResult:
    argv = [git_executable()]
    if repository is not None:
        argv.extend(["-C", str(repository)])
    argv.extend(str(value) for value in arguments)
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitCommandError(f"git command failed to execute: {' '.join(argv)}: {exc}") from exc
    wrapped = GitResult(tuple(argv), result.stdout, result.stderr, result.returncode)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise GitCommandError(f"git command failed ({result.returncode}): {' '.join(argv)}: {detail}")
    return wrapped


def is_repository(path: Path) -> bool:
    if not path.is_dir():
        return False
    result = run_git(path, ["rev-parse", "--is-inside-work-tree"], check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def ensure_clean(path: Path) -> None:
    if not is_repository(path):
        raise GitCommandError(f"not a git repository: {path}")
    status = run_git(path, ["status", "--porcelain=v1", "--untracked-files=all"]).stdout.strip()
    if status:
        raise GitCommandError(f"upstream repository is not clean: {path}\n{status}")


def current_commit(path: Path) -> str:
    return run_git(path, ["rev-parse", "HEAD"]).stdout.strip()


def resolve_commit(path: Path, revision: str) -> str:
    commit = run_git(path, ["rev-parse", "--verify", f"{revision}^{{commit}}"]).stdout.strip()
    if len(commit) != 40:
        raise GitCommandError(f"revision did not resolve to a full commit: {revision!r}")
    return commit


def fetch_tags(path: Path, remote: str = "origin") -> None:
    ensure_clean(path)
    run_git(path, ["fetch", "--tags", "--prune", remote], timeout=600.0)
    ensure_clean(path)


def clone_repository(repository: str | Path, destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise GitCommandError(f"clone destination is not empty: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_git(None, ["clone", "--no-hardlinks", str(repository), str(destination)], timeout=600.0)
    ensure_clean(destination)


def clone_at_revision(source: Path, destination: Path, revision: str) -> str:
    clone_repository(source, destination)
    commit = resolve_commit(destination, revision)
    run_git(destination, ["checkout", "--detach", commit])
    ensure_clean(destination)
    return commit


def checkout_clean_revision(path: Path, revision: str) -> str:
    ensure_clean(path)
    commit = resolve_commit(path, revision)
    run_git(path, ["checkout", "--detach", commit])
    ensure_clean(path)
    return commit


def describe_revision(path: Path, revision: str) -> str | None:
    result = run_git(path, ["describe", "--tags", "--exact-match", revision], check=False)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None
