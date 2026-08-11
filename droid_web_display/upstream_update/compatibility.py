from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Iterable

from .scaffold import adapter_directory_name, adapter_id


class PromotionError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionError(f"unable to read compatibility manifest: {exc}") from exc
    if not isinstance(value, dict):
        raise PromotionError("compatibility manifest root must be an object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _evidence(values: Iterable[str] | None) -> list[str]:
    return sorted({str(value) for value in values or [] if str(value).strip()})


def register_experimental_adapter(
    repo_root: Path,
    *,
    version: str,
    upstream_revision: str,
    upstream_commit: str,
    protocol_report: str,
    patch_series: list[dict[str, Any]] | None = None,
    server_sha256: str | None = None,
    server_path: str | None = None,
    automated_evidence: Iterable[str] | None = None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", upstream_commit):
        raise PromotionError("upstream commit must be a full 40-character lowercase SHA-1")
    manifest_path = repo_root / "compatibility" / "scrcpy-versions.json"
    manifest = _load(manifest_path)
    entries = manifest.setdefault("supportedVersions", {})
    key = adapter_id(version)
    if key in entries:
        raise PromotionError(f"compatibility entry already exists: {key}")
    default_before = manifest.get("defaultAdapter")
    entry: dict[str, Any] = {
        "repository": "https://github.com/Genymobile/scrcpy.git",
        "upstreamRevision": upstream_revision,
        "upstreamCommit": upstream_commit,
        "version": version,
        "adapterModule": f"versions/{adapter_directory_name(version)}",
        "status": "experimental",
        "baseAdapter": default_before,
        "patchSeries": patch_series or [],
        "protocolReport": protocol_report,
        "automatedEvidence": _evidence(automated_evidence),
        "browserEvidence": [],
        "hardwareEvidence": [],
        "knownLimitations": ["Not approved for default use until compatibility evidence is complete."],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    if server_sha256 is not None:
        if not re.fullmatch(r"[0-9a-f]{64}", server_sha256):
            raise PromotionError("server SHA-256 must contain 64 lowercase hexadecimal characters")
        entry["serverSha256"] = server_sha256
    if server_path:
        entry["serverPath"] = server_path
    entries[key] = entry
    if manifest.get("defaultAdapter") != default_before:
        raise PromotionError("experimental registration attempted to change the stable default adapter")
    _write(manifest_path, manifest)
    return {"adapterId": key, "defaultAdapter": default_before, **entry}


def promote_adapter(
    repo_root: Path,
    *,
    target_adapter: str,
    status: str,
    automated_evidence: Iterable[str] | None = None,
    browser_evidence: Iterable[str] | None = None,
    hardware_evidence: Iterable[str] | None = None,
    make_default: bool = False,
) -> dict[str, Any]:
    if status not in {"experimental", "candidate", "stable"}:
        raise PromotionError(f"unsupported compatibility status: {status}")
    manifest_path = repo_root / "compatibility" / "scrcpy-versions.json"
    manifest = _load(manifest_path)
    entry = manifest.get("supportedVersions", {}).get(target_adapter)
    if not isinstance(entry, dict):
        raise PromotionError(f"unknown adapter: {target_adapter}")

    automated = sorted(set(entry.get("automatedEvidence", [])) | set(_evidence(automated_evidence)))
    browser = sorted(set(entry.get("browserEvidence", [])) | set(_evidence(browser_evidence)))
    hardware = sorted(set(entry.get("hardwareEvidence", [])) | set(_evidence(hardware_evidence)))
    if status in {"candidate", "stable"} and not automated:
        raise PromotionError("candidate promotion requires automated compatibility evidence")
    if status == "stable":
        if not browser:
            raise PromotionError("stable promotion requires browser evidence")
        if not hardware:
            raise PromotionError("stable promotion requires Android hardware evidence")
        server_sha = str(entry.get("serverSha256", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", server_sha):
            raise PromotionError("stable promotion requires a verified matching server SHA-256")
        adapter_path = (
            repo_root
            / "packages"
            / "scrcpy-protocol"
            / "src"
            / str(entry.get("adapterModule", "")).replace("versions/", "versions/", 1)
        )
        if not adapter_path.is_dir():
            raise PromotionError(f"stable promotion requires an adapter implementation: {adapter_path}")

    entry["automatedEvidence"] = automated
    entry["browserEvidence"] = browser
    entry["hardwareEvidence"] = hardware
    entry["status"] = status
    entry["promotedAt"] = datetime.now(timezone.utc).isoformat()
    if make_default:
        if status != "stable":
            raise PromotionError("only a stable adapter may become the default")
        manifest["defaultAdapter"] = target_adapter
    _write(manifest_path, manifest)
    return {"adapterId": target_adapter, "defaultAdapter": manifest.get("defaultAdapter"), **entry}


def generate_compatibility_report(repo_root: Path, output_directory: Path) -> dict[str, str]:
    manifest_path = repo_root / "compatibility" / "scrcpy-versions.json"
    manifest = _load(manifest_path)
    output_directory.mkdir(parents=True, exist_ok=True)
    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "defaultAdapter": manifest.get("defaultAdapter"),
        "adapters": [],
    }
    for key, entry in sorted(manifest.get("supportedVersions", {}).items()):
        report["adapters"].append(
            {
                "adapterId": key,
                "version": entry.get("version"),
                "status": entry.get("status"),
                "upstreamCommit": entry.get("upstreamCommit"),
                "serverSha256": entry.get("serverSha256") or entry.get("officialReleaseServerSha256"),
                "automatedEvidenceCount": len(entry.get("automatedEvidence", entry.get("protocolEvidence", []))),
                "browserEvidenceCount": len(entry.get("browserEvidence", [])),
                "hardwareEvidenceCount": len(entry.get("hardwareEvidence", [])),
                "knownLimitations": entry.get("knownLimitations", []),
            }
        )
    json_path = output_directory / "compatibility-report.json"
    md_path = output_directory / "compatibility-report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = ["# scrcpy Compatibility Matrix", "", f"Default adapter: `{report['defaultAdapter']}`", ""]
    lines.append("| Adapter | Version | Status | Automated | Browser | Hardware |")
    lines.append("|---|---:|---|---:|---:|---:|")
    for item in report["adapters"]:
        lines.append(
            f"| `{item['adapterId']}` | {item['version']} | {item['status']} | "
            f"{item['automatedEvidenceCount']} | {item['browserEvidenceCount']} | {item['hardwareEvidenceCount']} |"
        )
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
