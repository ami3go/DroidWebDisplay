from __future__ import annotations

import json

from droid_web_display.desktop import update_check


class _Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_normalizes_project_release_tags() -> None:
    assert update_check.normalize_release_version("v0.11.2") == "0.11.2"
    assert update_check.normalize_release_version("stable-v0.11.3-rc.4") == "0.11.3rc4"


def test_release_order_handles_rc_and_final_versions() -> None:
    assert update_check.is_newer_release("0.11.2", "v0.11.3-rc.1")
    assert not update_check.is_newer_release("0.11.2", "stable-v0.11.2-rc.3")
    assert update_check.is_newer_release("0.11.2-rc.2", "v0.11.2")


def test_stable_channel_skips_prereleases(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = [
        {
            "tag_name": "stable-v0.12.0-rc.1",
            "name": "0.12.0 RC1",
            "html_url": "https://example.invalid/rc",
            "prerelease": True,
            "draft": False,
        },
        {
            "tag_name": "v0.11.3",
            "name": "0.11.3",
            "html_url": "https://example.invalid/stable",
            "prerelease": False,
            "draft": False,
        },
    ]
    monkeypatch.setattr(update_check, "urlopen", lambda *_args, **_kwargs: _Response(payload))
    result = update_check.check_latest_release("Stable")
    assert result.tag == "v0.11.3"
    assert not result.prerelease


def test_prerelease_channel_uses_highest_version(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = [
        {
            "tag_name": "v0.11.3",
            "html_url": "https://example.invalid/stable",
            "prerelease": False,
            "draft": False,
        },
        {
            "tag_name": "stable-v0.12.0-rc.2",
            "html_url": "https://example.invalid/rc",
            "prerelease": True,
            "draft": False,
        },
    ]
    monkeypatch.setattr(update_check, "urlopen", lambda *_args, **_kwargs: _Response(payload))
    result = update_check.check_latest_release("Pre-release")
    assert result.tag == "stable-v0.12.0-rc.2"
    assert result.version == "0.12.0rc2"
