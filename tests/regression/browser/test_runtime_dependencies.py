from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from droid_web_display import runtime


def test_websocket_runtime_dependency_is_declared() -> None:
    root = Path(__file__).resolve().parents[3]
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    assert any(item.startswith("websockets") or item.startswith("wsproto") for item in dependencies)


def test_runtime_preflight_accepts_installed_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "find_websocket_backend", lambda: "websockets")
    assert runtime.require_websocket_backend() == "websockets"


def test_runtime_preflight_has_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runtime, "find_websocket_backend", lambda: None)
    with pytest.raises(RuntimeError, match=r"uv sync --locked"):
        runtime.require_websocket_backend()
