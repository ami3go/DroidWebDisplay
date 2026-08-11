from __future__ import annotations

import json
from pathlib import Path
import tomllib

from droid_web_display import RELEASE_PHASE, __version__


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
