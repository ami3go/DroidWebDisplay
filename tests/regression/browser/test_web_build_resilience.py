from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from droid_web_display.release_checks import find_local_tsc, verify_static_client


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_bundled_static_client_matches_manifest() -> None:
    root = Path(__file__).resolve().parents[3]
    result = verify_static_client(root)
    assert result["status"] == "PASS", result
    assert result["checkedFiles"] > 10


def test_missing_compiler_does_not_delete_bundled_dist(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[3]
    node = shutil.which("node")
    if not node:
        return

    # Exercise the no-compiler release path in an isolated copy. This remains
    # valid even when a developer has already run npm ci in the real checkout.
    isolated = tmp_path / "repo"
    web_target = isolated / "apps/web-client"
    protocol_target = isolated / "packages/scrcpy-protocol"
    shutil.copytree(
        root / "apps/web-client",
        web_target,
        ignore=shutil.ignore_patterns("node_modules", ".dist-stage-*", ".dist-backup-*"),
    )
    shutil.copytree(root / "packages/scrcpy-protocol/dist", protocol_target / "dist")

    monkeypatch.delenv("DROID_WEB_DISPLAY_TSC", raising=False)
    assert find_local_tsc(isolated) is None
    before = _tree_hash(web_target / "dist")
    env = os.environ.copy()
    env.pop("DROID_WEB_DISPLAY_TSC", None)
    result = subprocess.run(
        [node, "tools/build.mjs"],
        cwd=web_target,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "TypeScript compiler is not installed" in (result.stdout + result.stderr)
    assert _tree_hash(web_target / "dist") == before
    assert verify_static_client(isolated)["status"] == "PASS"

