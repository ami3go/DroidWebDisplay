from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def load_tool(root: Path):
    path = root / "tools" / "download_server.py"
    spec = importlib.util.spec_from_file_location("download_server", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_download_path_is_canonical(tmp_path: Path, monkeypatch) -> None:
    payload = b"official-server"
    expected = hashlib.sha256(payload).hexdigest()
    source = tmp_path / "source.bin"
    source.write_bytes(payload)
    (tmp_path / "compatibility").mkdir()
    (tmp_path / "compatibility" / "scrcpy-versions.json").write_text(
        json.dumps({
            "defaultAdapter": "scrcpy-4.1",
            "supportedVersions": {
                "scrcpy-4.1": {
                    "version": "4.1",
                    "officialReleaseServerUrl": source.as_uri(),
                    "officialReleaseServerSha256": expected,
                }
            },
        }),
        encoding="utf-8",
    )
    repo_root = Path(__file__).resolve().parents[3]
    module = load_tool(repo_root)
    monkeypatch.setattr(sys, "argv", ["download_server.py", "--repo-root", str(tmp_path)])

    assert module.main() == 0
    output = tmp_path / "server" / "scrcpy-server-v4.1"
    assert output.read_bytes() == payload
    assert not (tmp_path / "server" / "scrcpy-server-v4.1.official").exists()
