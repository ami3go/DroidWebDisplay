from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
from typing import Any

from .build import build_matching_server
from .compatibility import PromotionError, promote_adapter, register_experimental_adapter
from .git import checkout_clean_revision, ensure_clean, run_git
from .inspection import inspect_protocol_changes
from .patches import PatchApplicationError, apply_patch_series
from .scaffold import scaffold_adapter


def _commit(repo: Path, message: str) -> str:
    run_git(repo, ["add", "."])
    run_git(repo, ["commit", "-m", message])
    return run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()


def run_self_test() -> dict[str, Any]:
    git = shutil.which("git")
    if not git:
        return {"status": "SKIP", "reason": "git executable not found"}
    with tempfile.TemporaryDirectory(prefix="droidwebdisplay-upstream-selftest-") as temp:
        root = Path(temp)
        upstream = root / "upstream"
        upstream.mkdir()
        run_git(upstream, ["init"])
        run_git(upstream, ["config", "user.email", "gate@example.invalid"])
        run_git(upstream, ["config", "user.name", "Gate 10"])
        options = upstream / "server/src/main/java/com/genymobile/scrcpy/Options.java"
        options.parent.mkdir(parents=True)
        options.write_text("class Options { int maxFps = 60; }\n", encoding="utf-8")
        base = _commit(upstream, "base")
        options.write_text("class Options { int maxFps = 120; int audioBitRate = 128000; }\n", encoding="utf-8")
        control = upstream / "server/src/main/java/com/genymobile/scrcpy/control/ControlMessage.java"
        control.parent.mkdir(parents=True)
        control.write_text("class ControlMessage { int clipboardAck; }\n", encoding="utf-8")
        target = _commit(upstream, "target")
        ensure_clean(upstream)
        inspection = inspect_protocol_changes(upstream, base, target)
        checkout_clean_revision(upstream, base)
        revision_selected = checkout_clean_revision(upstream, target) == target

        built_server = build_matching_server(
            upstream,
            revision=target,
            output=root / "scrcpy-server-v-test",
            command=[
                sys.executable,
                "-c",
                "from pathlib import Path; p=Path('server/build/outputs/apk/release'); "
                "p.mkdir(parents=True, exist_ok=True); (p/'server-release.apk').write_bytes(b'gate10-server')",
            ],
        )

        project = root / "project"
        base_adapter = project / "packages/scrcpy-protocol/src/versions/v4_1"
        base_adapter.mkdir(parents=True)
        (base_adapter / "index.ts").write_text("export const version = '4.1';\n", encoding="utf-8")
        compatibility = project / "compatibility"
        compatibility.mkdir(parents=True)
        manifest = {
            "schemaVersion": 1,
            "defaultAdapter": "scrcpy-4.1",
            "supportedVersions": {
                "scrcpy-4.1": {
                    "version": "4.1",
                    "adapterModule": "versions/v4_1",
                    "status": "stable",
                    "upstreamCommit": base,
                }
            },
        }
        (compatibility / "scrcpy-versions.json").write_text(json.dumps(manifest), encoding="utf-8")
        scaffold = scaffold_adapter(
            project,
            version="4.2",
            base_version="4.1",
            upstream_commit=target,
            protocol_report="report.json",
        )
        registered = register_experimental_adapter(
            project,
            version="4.2",
            upstream_revision=target,
            upstream_commit=target,
            protocol_report="report.json",
        )
        promotion_blocked = False
        try:
            promote_adapter(project, target_adapter="scrcpy-4.2", status="stable")
        except PromotionError:
            promotion_blocked = True

        patch_workspace = root / "patch-workspace"
        subprocess.run([git, "clone", str(upstream), str(patch_workspace)], check=True, capture_output=True)
        run_git(patch_workspace, ["checkout", "--detach", target])
        patch_dir = root / "patches"
        patch_dir.mkdir()
        (patch_dir / "001-invalid.patch").write_text("not a patch\n", encoding="utf-8")
        patch_failure_blocked = False
        try:
            apply_patch_series(patch_workspace, patch_dir)
        except PatchApplicationError:
            patch_failure_blocked = True
        ensure_clean(patch_workspace)

        checks = {
            "protocolAreasDetected": {
                "serverCommandLineOptions",
                "audioPacketAndCodec",
                "controlMessages",
                "clipboard",
            }.issubset({item["area"] for item in inspection["changedAreas"]}),
            "stableAdapterPreserved": registered["defaultAdapter"] == "scrcpy-4.1",
            "separateAdapterCreated": Path(scaffold["path"]).name == "v4_2",
            "experimentalByDefault": registered["status"] == "experimental",
            "stablePromotionBlockedWithoutEvidence": promotion_blocked,
            "patchFailureStopsAndResets": patch_failure_blocked,
            "revisionSelectionClean": revision_selected,
            "matchingServerBuilt": built_server.get("status") == "PASS" and len(str(built_server.get("sha256", ""))) == 64,
            "upstreamClean": True,
        }
        return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
