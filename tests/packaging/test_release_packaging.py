from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

from droid_web_display.release_packaging import (
    ReleaseInputs,
    build_release_tree,
    migrate_runtime_state,
    validate_release_tree,
)


def _minimal_release_repo(source_root: Path, target: Path, server_content: bytes) -> Path:
    target.mkdir(parents=True)
    for relative in (
        "droid_web_display",
        "apps/web-client/dist",
        "apps/web-client/dist-manifest.json",
        "packages/scrcpy-protocol/dist",
        "packages/scrcpy-protocol/package.json",
        "patches/scrcpy",
        "tools/run_bridge_service.py",
        "tools/stop_bridge_service.py",
        "tools/reset_auth.py",
        "tools/reset_network_access.py",
        "tools/migrate_config.py",
        "pyproject.toml",
        "requirements-lock.txt",
        "requirements-runtime.txt",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "packaging/windows",
        "packaging/linux",
    ):
        src = source_root / relative
        dst = target / relative
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    digest = hashlib.sha256(server_content).hexdigest()
    compatibility = {
        "schemaVersion": 2,
        "defaultAdapter": "scrcpy-4.1",
        "supportedVersions": {
            "scrcpy-4.1": {
                "version": "4.1",
                "status": "stable",
                "upstreamCommit": "test",
                "serverSha256": digest,
                "officialReleaseServerSha256": hashlib.sha256(b"official-base").hexdigest(),
                "officialReleaseServerUrl": "https://example.invalid/server",
                "serverProvenance": "droidwebdisplay-patched",
                "patchSeries": [{"path": "patches/scrcpy/test.patch", "sha256": "a" * 64}],
            }
        },
    }
    path = target / "compatibility/scrcpy-versions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(compatibility), encoding="utf-8")
    return target


def test_release_tree_verifies_server_and_excludes_runtime_state(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2]
    server_content = b"verified-test-server"
    repo = _minimal_release_repo(source, tmp_path / "repo", server_content)
    server = tmp_path / "server"
    server.write_bytes(server_content)
    (repo / "data").mkdir()
    (repo / "data/auth.json").write_text("secret", encoding="utf-8")
    output = tmp_path / "release"
    result = build_release_tree(repo, output, ReleaseInputs(target="windows", scrcpy_server=server))
    assert result["manifest"]["scrcpy"]["server"]["present"] is True
    assert result["manifest"]["scrcpy"]["server"]["serverProvenance"] == "droidwebdisplay-patched"
    assert result["manifest"]["scrcpy"]["server"]["patchSeries"]
    assert (output / "DroidWebDisplay.ps1").is_file()
    assert (output / "packaging/windows/install.ps1").is_file()
    assert (output / "tools/stop_bridge_service.py").is_file()
    assert (output / "pyproject.toml").is_file()
    assert not (output / "installer").exists()
    assert not (output / "data/auth.json").exists()
    assert validate_release_tree(output)["status"] == "PASS"


def test_offline_ready_requires_server_runtime_and_adb(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2]
    server_content = b"verified-test-server"
    repo = _minimal_release_repo(source, tmp_path / "repo", server_content)
    server = tmp_path / "server"
    server.write_bytes(server_content)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "python.exe").write_bytes(b"python")
    adb = tmp_path / "adb"
    adb.mkdir()
    (adb / "adb.exe").write_bytes(b"adb")
    output = tmp_path / "release"
    build_release_tree(repo, output, ReleaseInputs(target="windows", scrcpy_server=server, adb_directory=adb, python_runtime=runtime))
    assert validate_release_tree(output, require_offline_ready=True)["status"] == "PASS"


def test_configuration_migration_preserves_supported_state_only(tmp_path: Path) -> None:
    previous = tmp_path / "old"
    new = tmp_path / "new"
    (previous / "data/tls").mkdir(parents=True)
    (previous / "data/auth.json").write_text('{"auth":1}', encoding="utf-8")
    (previous / "data/network-access.json").write_text('{"network":1}', encoding="utf-8")
    (previous / "data/tls/cert.pem").write_text("cert", encoding="utf-8")
    (previous / "data/private.tmp").write_text("ignore", encoding="utf-8")
    result = migrate_runtime_state(previous, new)
    assert "auth.json" in result["copied"]
    assert (new / "data/auth.json").is_file()
    assert (new / "data/network-access.json").is_file()
    assert (new / "data/tls/cert.pem").is_file()
    assert not (new / "data/private.tmp").exists()
