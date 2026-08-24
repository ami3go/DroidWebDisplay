from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from droid_web_display.upstream_update.compatibility import PromotionError, promote_adapter, register_experimental_adapter
from droid_web_display.upstream_update.build import _find_server_artifact
from droid_web_display.upstream_update.git import ensure_clean, run_git
from droid_web_display.upstream_update.inspection import inspect_protocol_changes, write_protocol_report
from droid_web_display.upstream_update.patches import PatchApplicationError, apply_patch_series
from droid_web_display.upstream_update.scaffold import AdapterScaffoldError, scaffold_adapter
from droid_web_display.upstream_update.selftest import run_self_test


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True)
    run_git(path, ["init"])
    run_git(path, ["config", "user.email", "test@example.invalid"])
    run_git(path, ["config", "user.name", "Gate 10 Test"])


def _commit(path: Path, message: str) -> str:
    run_git(path, ["add", "."])
    run_git(path, ["commit", "-m", message])
    return run_git(path, ["rev-parse", "HEAD"]).stdout.strip()


def _project(path: Path, base_commit: str) -> Path:
    adapter = path / "packages/scrcpy-protocol/src/versions/v4_1"
    adapter.mkdir(parents=True)
    (adapter / "index.ts").write_text("export const version = '4.1';\n", encoding="utf-8")
    compatibility = path / "compatibility"
    compatibility.mkdir(parents=True)
    manifest = {
        "schemaVersion": 1,
        "defaultAdapter": "scrcpy-4.1",
        "supportedVersions": {
            "scrcpy-4.1": {
                "version": "4.1",
                "adapterModule": "versions/v4_1",
                "status": "stable",
                "upstreamCommit": base_commit,
            }
        },
    }
    (compatibility / "scrcpy-versions.json").write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_protocol_inspection_identifies_relevant_areas(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    _init_repo(upstream)
    options = upstream / "server/src/main/java/com/genymobile/scrcpy/Options.java"
    options.parent.mkdir(parents=True)
    options.write_text("class Options { int maxFps = 60; }\n", encoding="utf-8")
    base = _commit(upstream, "base")
    options.write_text("class Options { int maxFps = 120; int audioBitRate = 128000; }\n", encoding="utf-8")
    control = upstream / "server/src/main/java/com/genymobile/scrcpy/control/ControlMessage.java"
    control.parent.mkdir(parents=True)
    control.write_text("class ControlMessage { int clipboardAck; }\n", encoding="utf-8")
    target = _commit(upstream, "target")

    report = inspect_protocol_changes(upstream, base, target)
    areas = {entry["area"] for entry in report["changedAreas"]}
    assert {"serverCommandLineOptions", "audioPacketAndCodec", "controlMessages", "clipboard"}.issubset(areas)
    paths = write_protocol_report(report, tmp_path / "report")
    assert Path(paths["json"]).is_file()
    assert Path(paths["markdown"]).is_file()
    ensure_clean(upstream)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_adapter_scaffold_is_separate_and_promotion_is_evidence_gated(tmp_path: Path) -> None:
    commit = "a" * 40
    project = _project(tmp_path / "project", commit)
    result = scaffold_adapter(project, version="4.2", base_version="4.1", upstream_commit="b" * 40)
    assert Path(result["path"]).name == "v4_2"
    assert (project / "packages/scrcpy-protocol/src/versions/v4_1/index.ts").is_file()
    with pytest.raises(AdapterScaffoldError):
        scaffold_adapter(project, version="4.2", base_version="4.1", upstream_commit="b" * 40)

    registered = register_experimental_adapter(
        project,
        version="4.2",
        upstream_revision="v4.2",
        upstream_commit="b" * 40,
        protocol_report="protocol-change-report.json",
    )
    assert registered["status"] == "experimental"
    assert registered["defaultAdapter"] == "scrcpy-4.1"
    with pytest.raises(PromotionError, match="automated"):
        promote_adapter(project, target_adapter="scrcpy-4.2", status="candidate")
    candidate = promote_adapter(
        project,
        target_adapter="scrcpy-4.2",
        status="candidate",
        automated_evidence=["gate-automated.json"],
    )
    assert candidate["status"] == "candidate"
    with pytest.raises(PromotionError, match="browser"):
        promote_adapter(project, target_adapter="scrcpy-4.2", status="stable")


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_patch_failure_stops_and_resets_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _init_repo(workspace)
    target = workspace / "file.txt"
    target.write_text("base\n", encoding="utf-8")
    _commit(workspace, "base")
    patch_dir = tmp_path / "patches"
    patch_dir.mkdir()
    (patch_dir / "001-invalid.patch").write_text("not a patch\n", encoding="utf-8")
    with pytest.raises(PatchApplicationError):
        apply_patch_series(workspace, patch_dir)
    assert target.read_text(encoding="utf-8") == "base\n"
    ensure_clean(workspace)


def test_server_artifact_discovery_ignores_gradle_metadata(tmp_path: Path) -> None:
    release = tmp_path / "server/build/outputs/apk/release"
    release.mkdir(parents=True)
    apk = release / "server-release-unsigned.apk"
    apk.write_bytes(b"android-server")
    metadata = release / "output-metadata.json"
    metadata.write_text('{"artifactType":"APK"}\n', encoding="utf-8")
    metadata.touch()

    assert _find_server_artifact(tmp_path) == apk


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_phase10_selftest_passes() -> None:
    result = run_self_test()
    assert result["status"] == "PASS", result

@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_update_cli_keeps_stable_default_and_registers_experimental(tmp_path: Path) -> None:
    import subprocess
    import sys

    repo_root = Path(__file__).resolve().parents[2]
    upstream = tmp_path / "upstream"
    _init_repo(upstream)
    options = upstream / "server/src/main/java/com/genymobile/scrcpy/Options.java"
    options.parent.mkdir(parents=True)
    options.write_text("class Options { int maxFps = 60; }\n", encoding="utf-8")
    base = _commit(upstream, "base")
    options.write_text("class Options { int maxFps = 120; }\n", encoding="utf-8")
    target = _commit(upstream, "target")

    project = _project(tmp_path / "project", base)
    patch_dir = tmp_path / "patches"
    patch_dir.mkdir()
    report_dir = tmp_path / "reports"
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "tools/update_scrcpy.py"),
            "--repo-root",
            str(project),
            "--source-dir",
            str(upstream),
            "--target",
            target,
            "--version",
            "4.2",
            "--patch-dir",
            str(patch_dir),
            "--report-dir",
            str(report_dir),
            "--scaffold-adapter",
            "--register",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    manifest = json.loads((project / "compatibility/scrcpy-versions.json").read_text(encoding="utf-8"))
    assert manifest["defaultAdapter"] == "scrcpy-4.1"
    assert manifest["supportedVersions"]["scrcpy-4.2"]["status"] == "experimental"
    assert (project / "packages/scrcpy-protocol/src/versions/v4_2/adapter-scaffold.json").is_file()
    assert (report_dir / "protocol-change-report.json").is_file()
    assert (report_dir / "compatibility-report.json").is_file()
    ensure_clean(upstream)
