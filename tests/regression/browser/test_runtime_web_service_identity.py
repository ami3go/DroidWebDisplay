from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
LAUNCHER_PATH = ROOT / "tools" / "run_bridge_service.py"
SPEC = importlib.util.spec_from_file_location("droidwebdisplay_run_bridge_service", LAUNCHER_PATH)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def test_repository_web_root_carries_runtime_identity_markers() -> None:
    html = (ROOT / "apps" / "web-client" / "dist" / "index.html").read_text(encoding="utf-8")
    assert launcher.PRODUCT_TITLE_MARKER in html
    assert launcher.WEB_UI_MARKER in html
    assert launcher._is_current_web_ui(html) is True


def test_existing_current_droidwebdisplay_listener_is_identified(monkeypatch: pytest.MonkeyPatch) -> None:
    current_html = f"<html><head>{launcher.PRODUCT_TITLE_MARKER}</head><body data-ui='{launcher.WEB_UI_MARKER}'></body></html>"
    monkeypatch.setattr(launcher, "_port_is_listening", lambda host, port: True)
    monkeypatch.setattr(launcher, "_fetch_root_html", lambda url: current_html)

    assert launcher._classify_existing_service("http://127.0.0.1:8765/", "127.0.0.1", 8765) == "current"


def test_existing_legacy_or_unrelated_listener_is_not_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    legacy_html = "<html><head><title>GPT Bridge</title></head><body><h1>Unlock gpt-bridge</h1></body></html>"
    monkeypatch.setattr(launcher, "_port_is_listening", lambda host, port: True)
    monkeypatch.setattr(launcher, "_fetch_root_html", lambda url: legacy_html)

    assert launcher._classify_existing_service("http://127.0.0.1:8765/", "127.0.0.1", 8765) == "other"


def test_free_port_does_not_probe_or_match_a_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "_port_is_listening", lambda host, port: False)

    def unexpected_fetch(url: str) -> str:
        raise AssertionError(f"root HTML should not be fetched when the port is free: {url}")

    monkeypatch.setattr(launcher, "_fetch_root_html", unexpected_fetch)
    assert launcher._classify_existing_service("http://127.0.0.1:8765/", "127.0.0.1", 8765) == "none"


def test_wildcard_bind_addresses_probe_loopback() -> None:
    assert launcher._probe_host("0.0.0.0") == "127.0.0.1"
    assert launcher._probe_host("::") == "::1"
