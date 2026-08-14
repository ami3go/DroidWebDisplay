from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "packaging" / "supply-chain-lock.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


def test_supply_chain_lock_is_complete_and_fail_closed() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    assert lock["schemaVersion"] == 1
    assert lock["tools"]["python"] == "3.11.15"
    assert lock["tools"]["node"] == "22.23.2"
    assert lock["tools"]["uv"] == "0.12.4"
    assert lock["tools"]["pyinstaller"] == "6.21.0"

    for action in lock["githubActions"].values():
        assert action["repository"].startswith("actions/")
        assert COMMIT_RE.fullmatch(action["ref"])

    for key, artifact in lock["artifacts"].items():
        assert artifact["url"].startswith("https://"), key
        assert SHA256_RE.fullmatch(artifact["sha256"]), key
        assert artifact.get("version"), key
        if "latest" in artifact["url"] or "/continuous/" in artifact["url"]:
            assert artifact.get("version"), key
        if "/continuous/" in artifact["url"]:
            assert COMMIT_RE.fullmatch(artifact.get("sourceCommit", "")), key
        if key.startswith("android-platform-tools-"):
            assert artifact["zipRevision"] == artifact["version"]
            assert artifact["zipRevisionPath"] == "platform-tools/source.properties"


def test_release_workflow_uses_only_pinned_actions_and_verified_artifact_fetches() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    assert "curl -LsSf https://astral.sh/uv/install.sh | sh" not in workflow
    assert "platform-tools-latest-" not in workflow
    assert "releases/download/continuous/appimagetool" not in workflow
    assert "windows-latest" not in workflow
    assert "windows-2025" in workflow
    assert "python-version: '3.11.15'" in workflow
    assert "node-version: '22.23.2'" in workflow
    assert "--runtime-file" in workflow

    action_refs = re.findall(r"uses:\s+(actions/[A-Za-z0-9_.-]+)@([0-9A-Za-z_.-]+)", workflow)
    assert action_refs
    expected = {
        (entry["repository"], entry["ref"])
        for entry in lock["githubActions"].values()
    }
    for repository, ref in action_refs:
        assert COMMIT_RE.fullmatch(ref), (repository, ref)
        assert (repository, ref) in expected

    assert "tools/fetch_verified_artifact.py uv-linux-x86_64" in workflow
    assert "tools/fetch_verified_artifact.py android-platform-tools-windows" in workflow
    assert "tools/fetch_verified_artifact.py android-platform-tools-linux" in workflow
    assert "tools/fetch_verified_artifact.py appimagetool-linux-x86_64" in workflow
    assert "tools/fetch_verified_artifact.py appimage-runtime-linux-x86_64" in workflow
    assert "tools/generate_sbom.py" in workflow


def test_temporary_supply_chain_probe_is_not_tracked() -> None:
    assert not (ROOT / ".github" / "workflows" / "supply-chain-probe.yml").exists()
