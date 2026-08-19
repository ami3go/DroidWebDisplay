from __future__ import annotations

import json
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


def test_private_node_packages_do_not_define_product_version() -> None:
    package_paths = ("apps/web-client/package.json", "packages/scrcpy-protocol/package.json")
    lock_paths = ("apps/web-client/package-lock.json", "packages/scrcpy-protocol/package-lock.json")
    for relative in package_paths:
        package = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        assert package["private"] is True
        assert package["version"] == "0.0.0"
    for relative in lock_paths:
        lock = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        assert lock["version"] == "0.0.0"
        assert lock["packages"][""]["version"] == "0.0.0"
    web_lock = json.loads((ROOT / "apps/web-client/package-lock.json").read_text(encoding="utf-8"))
    assert web_lock["packages"]["../../packages/scrcpy-protocol"]["version"] == "0.0.0"


def test_web_build_reads_product_version_from_root_and_stamps_assets() -> None:
    build = (ROOT / "apps/web-client/tools/build.mjs").read_text(encoding="utf-8")
    assert 'readFile(resolve(repo, "VERSION"), "utf8")' in build
    assert "packageVersion: productVersion" in build
    assert "stampStaticVersion(stage)" in build
    assert 'packageVersion: "0.11.2"' not in build
