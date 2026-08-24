import hashlib
import json
from pathlib import Path

import pytest

from droid_web_display.errors import ArtifactError
from droid_web_display.scrcpy.artifact import ScrcpyArtifact


def write_compatibility(root: Path, server_bytes: bytes) -> str:
    sha = hashlib.sha256(server_bytes).hexdigest()
    (root / "compatibility").mkdir()
    (root / "server").mkdir()
    (root / "compatibility" / "scrcpy-versions.json").write_text(
        json.dumps(
            {
                "defaultAdapter": "scrcpy-4.1",
                "supportedVersions": {
                    "scrcpy-4.1": {
                        "version": "4.1",
                        "upstreamCommit": "a" * 40,
                        "officialReleaseServerSha256": sha,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (root / "server" / "scrcpy-server-v4.1").write_bytes(server_bytes)
    return sha


def test_artifact_accepts_pinned_hash(tmp_path: Path) -> None:
    sha = write_compatibility(tmp_path, b"server")
    artifact = ScrcpyArtifact.from_repository(tmp_path)
    assert artifact.version == "4.1"
    assert artifact.sha256 == sha


def test_artifact_prefers_patched_server_hash_over_official_base(tmp_path: Path) -> None:
    patched = b"patched-server"
    sha = write_compatibility(tmp_path, patched)
    compatibility_path = tmp_path / "compatibility" / "scrcpy-versions.json"
    compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
    entry = compatibility["supportedVersions"]["scrcpy-4.1"]
    entry["serverSha256"] = sha
    entry["officialReleaseServerSha256"] = hashlib.sha256(b"official-base").hexdigest()
    compatibility_path.write_text(json.dumps(compatibility), encoding="utf-8")

    artifact = ScrcpyArtifact.from_repository(tmp_path)

    assert artifact.sha256 == sha


def test_incompatible_local_manifest_is_rejected(tmp_path: Path) -> None:
    sha = write_compatibility(tmp_path, b"server")
    (tmp_path / "server" / "scrcpy-server.manifest.json").write_text(
        json.dumps(
            {
                "sha256": sha,
                "scrcpyVersion": "4.0",
                "upstreamCommit": "b" * 40,
                "adapter": "scrcpy-4.0",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ArtifactError, match="incompatible"):
        ScrcpyArtifact.from_repository(tmp_path)


def test_artifact_accepts_legacy_official_filename(tmp_path: Path) -> None:
    server_bytes = b"server"
    sha = write_compatibility(tmp_path, server_bytes)
    canonical = tmp_path / "server" / "scrcpy-server-v4.1"
    legacy = tmp_path / "server" / "scrcpy-server-v4.1.official"
    canonical.replace(legacy)

    artifact = ScrcpyArtifact.from_repository(tmp_path)

    assert artifact.path == legacy.resolve()
    assert artifact.sha256 == sha
