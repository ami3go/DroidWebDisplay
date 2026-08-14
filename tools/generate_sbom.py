#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import re
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "evidence" / "supply-chain"
UNKNOWN = "UNKNOWN"


def _license_from_metadata(meta: metadata.PackageMetadata) -> str:
    expression = meta.get("License-Expression")
    if expression and expression.strip():
        return expression.strip()

    license_value = meta.get("License")
    if license_value and license_value.strip() and license_value.strip().upper() != UNKNOWN:
        return license_value.strip()

    classifiers = [
        value.removeprefix("License :: ").strip()
        for value in (meta.get_all("Classifier") or [])
        if value.startswith("License :: ")
    ]
    return " | ".join(sorted(set(classifiers))) if classifiers else UNKNOWN


def _pypi_purl(name: str, version: str) -> str:
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    return f"pkg:pypi/{quote(normalized, safe='')}@{quote(version, safe='')}"


def _npm_purl(name: str, version: str) -> str:
    return f"pkg:npm/{quote(name, safe='/')}@{quote(version, safe='')}"


def _github_purl(repository: str, ref: str) -> str:
    return f"pkg:github/{repository}@{ref}"


def _component(
    *,
    ecosystem: str,
    name: str,
    version: str,
    license_name: str = UNKNOWN,
    purl: str | None = None,
    source: str,
    component_type: str = "library",
    hashes: list[dict[str, str]] | None = None,
    properties: list[dict[str, str]] | None = None,
    external_references: list[dict[str, str]] | None = None,
) -> tuple[dict[str, object], dict[str, str]]:
    bom_ref = f"{ecosystem}:{name}@{version}"
    component: dict[str, object] = {
        "bom-ref": bom_ref,
        "type": component_type,
        "name": name,
        "version": version,
        "properties": [
            {"name": "droidwebdisplay:ecosystem", "value": ecosystem},
            {"name": "droidwebdisplay:source", "value": source},
            *(properties or []),
        ],
    }
    if purl:
        component["purl"] = purl
    if license_name != UNKNOWN:
        component["licenses"] = [{"license": {"name": license_name}}]
    if hashes:
        component["hashes"] = hashes
    if external_references:
        component["externalReferences"] = external_references

    inventory = {
        "ecosystem": ecosystem,
        "name": name,
        "version": version,
        "license": license_name,
        "purl": purl or "",
        "source": source,
    }
    return component, inventory


def _python_components() -> list[tuple[dict[str, object], dict[str, str]]]:
    result: list[tuple[dict[str, object], dict[str, str]]] = []
    seen: set[tuple[str, str]] = set()
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        version = dist.version
        if not name or not version:
            continue
        key = (name.lower(), version)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            _component(
                ecosystem="python",
                name=name,
                version=version,
                license_name=_license_from_metadata(dist.metadata),
                purl=_pypi_purl(name, version),
                source="resolved-ci-environment",
            )
        )
    return result


def _npm_components(lock_path: Path) -> list[tuple[dict[str, object], dict[str, str]]]:
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    result: list[tuple[dict[str, object], dict[str, str]]] = []
    for package_path, package in sorted((data.get("packages") or {}).items()):
        if not package_path or not isinstance(package, dict) or package.get("link"):
            continue
        version = package.get("version")
        if not isinstance(version, str) or not version:
            continue
        name = package.get("name")
        if not isinstance(name, str) or not name:
            marker = "node_modules/"
            name = package_path.rsplit(marker, 1)[-1]
        license_name = package.get("license")
        if not isinstance(license_name, str) or not license_name.strip():
            license_name = UNKNOWN
        result.append(
            _component(
                ecosystem="npm",
                name=name,
                version=version,
                license_name=license_name,
                purl=_npm_purl(name, version),
                source=str(lock_path.relative_to(ROOT)),
                properties=[
                    {
                        "name": "droidwebdisplay:npm-dev-dependency",
                        "value": str(bool(package.get("dev"))).lower(),
                    }
                ],
            )
        )
    return result


def _supply_chain_components(lock_path: Path) -> list[tuple[dict[str, object], dict[str, str]]]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    result: list[tuple[dict[str, object], dict[str, str]]] = []

    for name, version in sorted((lock.get("tools") or {}).items()):
        result.append(
            _component(
                ecosystem="build-tool",
                name=name,
                version=str(version),
                source=str(lock_path.relative_to(ROOT)),
                component_type="application",
            )
        )

    for action_name, action in sorted((lock.get("githubActions") or {}).items()):
        repository = action["repository"]
        ref = action["ref"]
        result.append(
            _component(
                ecosystem="github-action",
                name=repository,
                version=action.get("label") or ref,
                purl=_github_purl(repository, ref),
                source=str(lock_path.relative_to(ROOT)),
                component_type="application",
                properties=[
                    {"name": "droidwebdisplay:lock-key", "value": action_name},
                    {"name": "droidwebdisplay:commit", "value": ref},
                ],
            )
        )

    for key, artifact in sorted((lock.get("artifacts") or {}).items()):
        properties = [{"name": "droidwebdisplay:lock-key", "value": key}]
        source_commit = artifact.get("sourceCommit")
        if source_commit:
            properties.append({"name": "droidwebdisplay:source-commit", "value": source_commit})
        result.append(
            _component(
                ecosystem="external-artifact",
                name=key,
                version=str(artifact.get("version") or "locked"),
                license_name=str(artifact.get("license") or UNKNOWN),
                source=str(lock_path.relative_to(ROOT)),
                component_type="application",
                hashes=[{"alg": "SHA-256", "content": artifact["sha256"]}],
                properties=properties,
                external_references=[
                    {"type": "distribution", "url": artifact["url"]},
                ],
            )
        )
    return result


def _scrcpy_component() -> tuple[dict[str, object], dict[str, str]]:
    manifest_path = ROOT / "compatibility" / "scrcpy-versions.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["supportedVersions"][manifest["defaultAdapter"]]
    version = str(entry["version"])
    tag = str(entry["upstreamTag"])
    return _component(
        ecosystem="scrcpy",
        name="scrcpy-server",
        version=version,
        license_name="Apache-2.0",
        purl=_github_purl("Genymobile/scrcpy", tag),
        source=str(manifest_path.relative_to(ROOT)),
        component_type="application",
        hashes=[{"alg": "SHA-256", "content": entry["officialReleaseServerSha256"]}],
        properties=[
            {"name": "droidwebdisplay:upstream-commit", "value": entry["upstreamCommit"]},
        ],
        external_references=[
            {"type": "distribution", "url": entry["officialReleaseServerUrl"]},
        ],
    )


def _deduplicate(
    entries: list[tuple[dict[str, object], dict[str, str]]]
) -> list[tuple[dict[str, object], dict[str, str]]]:
    by_ref: dict[str, tuple[dict[str, object], dict[str, str]]] = {}
    for component, inventory in entries:
        by_ref[str(component["bom-ref"])] = (component, inventory)
    return [by_ref[key] for key in sorted(by_ref)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DroidWebDisplay build SBOM and license inventory")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--supply-chain-lock",
        type=Path,
        default=ROOT / "packaging" / "supply-chain-lock.json",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    git_sha = os.environ.get("GITHUB_SHA", "").strip()

    entries: list[tuple[dict[str, object], dict[str, str]]] = []
    entries.extend(_python_components())
    entries.extend(_npm_components(ROOT / "packages" / "scrcpy-protocol" / "package-lock.json"))
    entries.extend(_npm_components(ROOT / "apps" / "web-client" / "package-lock.json"))
    entries.extend(_supply_chain_components(args.supply_chain_lock.resolve()))
    entries.append(_scrcpy_component())
    entries = _deduplicate(entries)

    metadata_properties = [
        {"name": "droidwebdisplay:inventory-scope", "value": "resolved CI/build environment"},
    ]
    if git_sha:
        metadata_properties.append({"name": "droidwebdisplay:git-sha", "value": git_sha})

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "timestamp": timestamp,
            "component": {
                "type": "application",
                "name": "DroidWebDisplay",
                "version": version,
            },
            "properties": metadata_properties,
        },
        "components": [component for component, _ in entries],
    }
    inventory = {
        "schemaVersion": 1,
        "generatedAt": timestamp,
        "project": {"name": "DroidWebDisplay", "version": version, "gitSha": git_sha or None},
        "scope": "resolved CI/build environment",
        "items": [item for _, item in entries],
    }

    sbom_path = output_dir / "build-sbom.cdx.json"
    inventory_path = output_dir / "license-inventory.json"
    sbom_path.write_text(json.dumps(sbom, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inventory_path.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(entries)} SBOM components to {sbom_path}")
    print(f"Wrote license inventory to {inventory_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
