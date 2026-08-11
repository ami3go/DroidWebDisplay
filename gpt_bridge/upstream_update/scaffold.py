from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
from typing import Any


class AdapterScaffoldError(RuntimeError):
    pass


_VERSION_RE = re.compile(r"^[0-9]+(?:\.[0-9]+){1,2}(?:[-+][0-9A-Za-z.-]+)?$")


def adapter_directory_name(version: str) -> str:
    if not _VERSION_RE.fullmatch(version):
        raise AdapterScaffoldError(f"invalid scrcpy version: {version!r}")
    normalized = re.sub(r"[^0-9A-Za-z]+", "_", version).strip("_")
    return f"v{normalized}"


def adapter_id(version: str) -> str:
    adapter_directory_name(version)
    return f"scrcpy-{version}"


def scaffold_adapter(
    repo_root: Path,
    *,
    version: str,
    base_version: str,
    upstream_commit: str,
    protocol_report: str | None = None,
) -> dict[str, Any]:
    package_root = repo_root / "packages" / "scrcpy-protocol"
    source_root = package_root / "src" / "versions"
    base = source_root / adapter_directory_name(base_version)
    destination = source_root / adapter_directory_name(version)
    if not base.is_dir():
        raise AdapterScaffoldError(f"base adapter does not exist: {base}")
    if destination.exists():
        raise AdapterScaffoldError(f"refusing to overwrite adapter scaffold: {destination}")
    if not re.fullmatch(r"[0-9a-f]{40}", upstream_commit):
        raise AdapterScaffoldError("upstream commit must be a full 40-character lowercase SHA-1")

    shutil.copytree(base, destination)
    metadata = {
        "schemaVersion": 1,
        "adapterId": adapter_id(version),
        "adapterDirectory": destination.name,
        "version": version,
        "status": "experimental",
        "baseAdapter": adapter_id(base_version),
        "baseVersion": base_version,
        "upstreamCommit": upstream_commit,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "protocolReport": protocol_report,
        "stablePromotionAllowed": False,
    }
    (destination / "adapter-scaffold.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (destination / "UPSTREAM_UPDATE.md").write_text(
        "\n".join(
            [
                f"# Experimental scrcpy {version} adapter",
                "",
                f"Copied from the stable scrcpy {base_version} adapter as an isolated starting point.",
                f"Target upstream commit: `{upstream_commit}`.",
                "",
                "The copied implementation is not evidence of compatibility. Review every area in the generated protocol report,",
                "update fixtures and source references, and record automated, browser, and hardware evidence before promotion.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {**metadata, "path": str(destination)}
