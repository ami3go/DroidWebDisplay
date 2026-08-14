from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def _project_version() -> str:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(pyproject["project"]["version"])


def test_top_level_version_matches_pyproject() -> None:
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == _project_version()


def test_runtime_requirements_header_matches_project_version() -> None:
    first_line = (ROOT / "requirements-runtime.txt").read_text(encoding="utf-8").splitlines()[0]
    assert first_line == f"# DroidWebDisplay v{_project_version()} pinned runtime environment."
