#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from droid_web_display.upstream_update.build import build_matching_server
from droid_web_display.upstream_update.compatibility import generate_compatibility_report, register_experimental_adapter
from droid_web_display.upstream_update.git import (
    checkout_clean_revision,
    clone_repository,
    current_commit,
    describe_revision,
    ensure_clean,
    fetch_tags,
    is_repository,
    resolve_commit,
)
from droid_web_display.upstream_update.inspection import inspect_protocol_changes, write_protocol_report
from droid_web_display.upstream_update.patches import discover_patch_series
from droid_web_display.upstream_update.scaffold import scaffold_adapter


def _load_manifest(root: Path) -> dict[str, Any]:
    path = root / "compatibility/scrcpy-versions.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("compatibility manifest root must be an object")
    return value


def _version_from_target(source: Path, target: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    tag = describe_revision(source, target)
    candidate = tag or target
    match = re.fullmatch(r"v?([0-9]+\.[0-9]+(?:\.[0-9]+)?)", candidate)
    if not match:
        raise RuntimeError("--version is required when the target is not an exact vX.Y or vX.Y.Z tag")
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a controlled scrcpy upstream update")
    parser.add_argument("--target", required=True, help="Target upstream tag or commit")
    parser.add_argument("--version", help="Target scrcpy version; inferred from exact vX.Y tags")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "third_party/scrcpy")
    parser.add_argument("--repository", default="https://github.com/Genymobile/scrcpy.git")
    parser.add_argument("--clone-if-missing", action="store_true")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--select-source", action="store_true", help="Move the clean source checkout to the target revision")
    parser.add_argument("--patch-dir", type=Path, default=ROOT / "patches/scrcpy")
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--scaffold-adapter", action="store_true")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--build-server", action="store_true")
    parser.add_argument("--server-output", type=Path)
    parser.add_argument("--automated-evidence", action="append", default=[])
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()

    root = args.repo_root.resolve()
    source = args.source_dir.resolve()
    if not is_repository(source):
        if not args.clone_if_missing:
            raise RuntimeError(
                f"scrcpy source repository is missing at {source}; initialize the submodule or pass --clone-if-missing"
            )
        if source.exists():
            if any(source.iterdir()):
                raise RuntimeError(f"cannot clone into non-empty source directory: {source}")
            source.rmdir()
        clone_repository(args.repository, source)
    ensure_clean(source)
    if args.fetch:
        fetch_tags(source)

    manifest = _load_manifest(root)
    stable_id = manifest.get("defaultAdapter")
    stable = manifest.get("supportedVersions", {}).get(stable_id)
    if not isinstance(stable, dict):
        raise RuntimeError(f"stable adapter entry is missing: {stable_id!r}")
    base_commit = str(stable.get("upstreamCommit", ""))
    base_version = str(stable.get("version", ""))
    target_commit = resolve_commit(source, args.target)
    version = _version_from_target(source, args.target, args.version)
    safe_target = re.sub(r"[^0-9A-Za-z._-]+", "_", version)
    report_dir = (args.report_dir or root / "evidence/upstream" / f"scrcpy-{safe_target}").resolve()

    protocol = inspect_protocol_changes(source, base_commit, target_commit)
    reports = write_protocol_report(protocol, report_dir)
    patch_paths = discover_patch_series(args.patch_dir.resolve() if args.patch_dir else None)
    patch_records = [{"path": str(path.resolve())} for path in patch_paths]

    scaffold: dict[str, Any] | None = None
    if args.scaffold_adapter:
        scaffold = scaffold_adapter(
            root,
            version=version,
            base_version=base_version,
            upstream_commit=target_commit,
            protocol_report=reports["json"],
        )

    server: dict[str, Any] | None = None
    if args.build_server:
        output = (args.server_output or root / "server" / f"scrcpy-server-v{version}.experimental").resolve()
        server = build_matching_server(
            source,
            revision=target_commit,
            output=output,
            patch_directory=args.patch_dir.resolve() if args.patch_dir else None,
        )

    registered: dict[str, Any] | None = None
    if args.register:
        if scaffold is None:
            raise RuntimeError("--register requires --scaffold-adapter so the experimental adapter exists separately")
        registered = register_experimental_adapter(
            root,
            version=version,
            upstream_revision=args.target,
            upstream_commit=target_commit,
            protocol_report=reports["json"],
            patch_series=server.get("patchSeries", patch_records) if server else patch_records,
            server_sha256=server.get("sha256") if server else None,
            server_path=server.get("artifact") if server else None,
            automated_evidence=args.automated_evidence,
        )

    selected_commit = current_commit(source)
    if args.select_source:
        selected_commit = checkout_clean_revision(source, target_commit)
    ensure_clean(source)
    compatibility_reports = generate_compatibility_report(root, report_dir)
    summary = {
        "schemaVersion": 1,
        "status": "PASS",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "stableAdapter": stable_id,
        "stableAdapterUnchanged": manifest.get("defaultAdapter") == stable_id,
        "baseVersion": base_version,
        "baseCommit": base_commit,
        "targetVersion": version,
        "targetRevision": args.target,
        "targetCommit": target_commit,
        "sourceCommitAfterRun": selected_commit,
        "sourceClean": True,
        "protocolReports": reports,
        "compatibilityReports": compatibility_reports,
        "scaffold": scaffold,
        "serverBuild": server,
        "registered": registered,
    }
    summary_path = report_dir / "update-summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({**summary, "summary": str(summary_path)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
