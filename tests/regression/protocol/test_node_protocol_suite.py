from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_ROOT = ROOT / "packages" / "scrcpy-protocol"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for the scrcpy protocol suite")
def test_precompiled_protocol_suite() -> None:
    result = subprocess.run(
        [shutil.which("node") or "node", "tools/run-tests.mjs"],
        cwd=PROTOCOL_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is required for fixture inspection")
def test_bundled_video_fixture_parses() -> None:
    result = subprocess.run(
        [
            shutil.which("node") or "node",
            "tools/inspect-fixture.mjs",
            "fixtures/video-startup-h264.bin",
            "--packet-count",
            "2",
        ],
        cwd=PROTOCOL_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"status": "PASS"' in result.stdout
    assert '"codec": "avc1.640028"' in result.stdout
