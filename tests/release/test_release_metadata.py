from __future__ import annotations

import json
from pathlib import Path
import tomllib

from fastapi.testclient import TestClient

from droid_web_display import RELEASE_PHASE, __version__
from droid_web_display.api import create_app
from droid_web_display.config import BridgeConfig


ROOT = Path(__file__).resolve().parents[2]


def test_release_version_metadata_is_consistent() -> None:
    assert __version__ == "0.11.2"
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == __version__

    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == __version__

    for relative in (
        "apps/web-client/package.json",
        "apps/web-client/package-lock.json",
        "packages/scrcpy-protocol/package.json",
        "packages/scrcpy-protocol/package-lock.json",
    ):
        payload = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        assert payload["version"] == __version__, relative
        if relative.endswith("package-lock.json"):
            assert payload["packages"][""]["version"] == __version__, relative


def test_release_phase_is_phase_11() -> None:
    assert RELEASE_PHASE == 11


def test_public_api_exposes_canonical_release_phase(tmp_path: Path) -> None:
    config = BridgeConfig(
        repo_root=ROOT,
        transfer_data_directory=tmp_path / "data",
        default_download_directory=tmp_path / "downloads",
        auth_data_file=tmp_path / "data" / "auth.json",
        network_config_file=tmp_path / "data" / "network-access.json",
        authentication_required=False,
    )
    app = create_app(config=config)

    with TestClient(app) as client:
        version = client.get("/api/v1/version")
        assert version.status_code == 200
        assert version.json()["phase"] == RELEASE_PHASE
        assert version.json()["version"] == __version__

        diagnostics = client.get("/api/v1/diagnostics")
        assert diagnostics.status_code == 200
        assert diagnostics.json()["phase"] == RELEASE_PHASE

        with client.websocket_connect("/ws/v1/events") as websocket:
            assert websocket.receive_json()["phase"] == RELEASE_PHASE
