from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_static_client(root: Path) -> dict[str, Any]:
    dist = root / "apps/web-client/dist"
    manifest_path = root / "apps/web-client/dist-manifest.json"
    errors: list[str] = []
    checked = 0
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest.get("files", []):
            path = dist / entry["path"]
            if not path.is_file():
                errors.append(f"missing: {entry['path']}")
            elif sha256(path) != entry["sha256"]:
                errors.append(f"checksum mismatch: {entry['path']}")
            checked += 1
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    for relative in (
        "index.html", "styles.css", "assets/main.js", "assets/auth-controller.js",
        "assets/api.js", "vendor/scrcpy-protocol/src/index.js",
    ):
        if not (dist / relative).is_file():
            errors.append(f"missing required runtime file: {relative}")
    return {
        "status": "PASS" if not errors else "FAIL",
        "checkedFiles": checked,
        "errors": errors,
        "manifest": str(manifest_path),
    }


def find_local_tsc(root: Path) -> Path | None:
    candidates = [
        Path(os.environ["GPT_BRIDGE_TSC"]) if os.environ.get("GPT_BRIDGE_TSC") else None,
        root / "apps/web-client/node_modules/typescript/bin/tsc",
        root / "packages/scrcpy-protocol/node_modules/typescript/bin/tsc",
    ]
    return next((path for path in candidates if path and path.is_file()), None)
