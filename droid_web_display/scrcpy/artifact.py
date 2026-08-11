from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from droid_web_display.errors import ArtifactError


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class ScrcpyArtifact:
    path: Path
    version: str
    upstream_commit: str
    sha256: str
    adapter_id: str

    @classmethod
    def from_repository(cls, repo_root: Path) -> "ScrcpyArtifact":
        compatibility_path = repo_root / "compatibility" / "scrcpy-versions.json"
        try:
            compatibility = json.loads(compatibility_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ArtifactError(f"Unable to read compatibility manifest: {exc}") from exc

        adapter_id = compatibility.get("defaultAdapter")
        entries = compatibility.get("supportedVersions", {})
        entry = entries.get(adapter_id)
        if not isinstance(entry, dict):
            raise ArtifactError(f"Compatibility entry is missing for {adapter_id!r}")

        version = str(entry.get("version", ""))
        expected_sha = str(entry.get("officialReleaseServerSha256", "")).lower()
        if len(expected_sha) != 64:
            raise ArtifactError("Expected scrcpy server SHA-256 is invalid")

        candidates = (
            repo_root / "server" / f"scrcpy-server-v{version}",
            repo_root / "server" / "scrcpy-server",
            # Backward compatibility for the v0.2.0 downloader naming defect.
            repo_root / "server" / f"scrcpy-server-v{version}.official",
        )
        artifact_path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if artifact_path is None:
            raise ArtifactError(
                "scrcpy server artifact is missing; install the pinned official server or run "
                "tools/download_official_server.py",
                details={"expectedCandidates": [str(path) for path in candidates]},
            )

        actual_sha = sha256_file(artifact_path)
        local_manifest_path = repo_root / "server" / "scrcpy-server.manifest.json"
        local_manifest: dict = {}
        if local_manifest_path.is_file():
            try:
                local_manifest = json.loads(local_manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ArtifactError(f"Invalid local server manifest: {exc}") from exc

        if local_manifest:
            declared_version = str(local_manifest.get("scrcpyVersion", ""))
            declared_commit = str(local_manifest.get("upstreamCommit", ""))
            declared_adapter = str(local_manifest.get("adapter", ""))
            mismatches: dict[str, dict[str, str]] = {}
            if declared_version and declared_version != version:
                mismatches["scrcpyVersion"] = {"expected": version, "actual": declared_version}
            expected_commit = str(entry.get("upstreamCommit", ""))
            if declared_commit and declared_commit != expected_commit:
                mismatches["upstreamCommit"] = {"expected": expected_commit, "actual": declared_commit}
            if declared_adapter and declared_adapter != adapter_id:
                mismatches["adapter"] = {"expected": str(adapter_id), "actual": declared_adapter}
            if mismatches:
                raise ArtifactError(
                    "Local scrcpy server manifest is incompatible with the selected adapter",
                    details={"mismatches": mismatches, "manifest": str(local_manifest_path)},
                )

        allowed_hashes = {expected_sha}
        local_sha = str(local_manifest.get("sha256", "")).lower()
        if len(local_sha) == 64:
            allowed_hashes.add(local_sha)
        if actual_sha not in allowed_hashes:
            raise ArtifactError(
                "scrcpy server checksum does not match the compatibility or local build manifest",
                details={
                    "artifact": str(artifact_path),
                    "actualSha256": actual_sha,
                    "allowedSha256": sorted(allowed_hashes),
                },
            )

        return cls(
            path=artifact_path.resolve(),
            version=version,
            upstream_commit=str(entry.get("upstreamCommit", "")),
            sha256=actual_sha,
            adapter_id=str(adapter_id),
        )
