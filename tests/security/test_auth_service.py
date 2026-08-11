from __future__ import annotations

import json
from pathlib import Path

import pytest

from droid_web_display.auth import AuthError, AuthService, TRUST_DURATIONS


class MutableClock:
    def __init__(self, value: float = 1_000_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def test_pin_is_slow_hashed_and_raw_tokens_are_not_persisted(tmp_path: Path) -> None:
    service = AuthService(tmp_path / "auth.json")
    grant = service.setup(
        "123456",
        duration="1-day",
        custom_seconds=None,
        user_agent="Mozilla/5.0 Firefox/153 Windows",
    )
    payload = json.loads((tmp_path / "auth.json").read_text(encoding="utf-8"))
    encoded = json.dumps(payload)
    assert payload["pin"]["algorithm"] == "pbkdf2-hmac-sha256"
    assert payload["pin"]["iterations"] == 600_000
    assert "123456" not in encoded
    assert grant.token not in encoded
    assert payload["sessions"][0]["tokenHash"]
    assert service.authenticate(grant.token) is not None


def test_every_required_trust_duration_and_custom_validation(tmp_path: Path) -> None:
    service = AuthService(tmp_path / "auth.json")
    first = service.setup("1234", duration="browser-session", custom_seconds=None, user_agent="test")
    assert first.cookie_max_age is None
    for choice in TRUST_DURATIONS:
        grant = service.login(
            "1234",
            duration=choice,
            custom_seconds=None,
            user_agent="test",
            client_key=f"client-{choice}",
        )
        assert grant.session["duration"] == choice
        if choice == "forever":
            assert grant.session["expiresAt"] is None
            assert grant.cookie_max_age is not None
    custom = service.login(
        "1234",
        duration="custom",
        custom_seconds=5 * 60,
        user_agent="test",
        client_key="custom",
    )
    assert custom.session["customSeconds"] == 300
    with pytest.raises(AuthError, match="between 5 minutes and 10 years"):
        service.login("1234", duration="custom", custom_seconds=299, user_agent="test", client_key="bad")


def test_expiration_and_individual_global_revocation(tmp_path: Path) -> None:
    clock = MutableClock()
    service = AuthService(tmp_path / "auth.json", clock=clock)
    first = service.setup("1234", duration="1-hour", custom_seconds=None, user_agent="first")
    second = service.login("1234", duration="1-day", custom_seconds=None, user_agent="second", client_key="second")
    assert service.authenticate(first.token) is not None
    clock.value += 3601
    assert service.authenticate(first.token) is None
    assert service.authenticate(second.token) is not None
    assert service.revoke(second.session["sessionId"], actor_session_id=second.session["sessionId"])
    assert service.authenticate(second.token) is None

    third = service.login("1234", duration="1-week", custom_seconds=None, user_agent="third", client_key="third")
    fourth = service.login("1234", duration="forever", custom_seconds=None, user_agent="fourth", client_key="fourth")
    assert service.revoke_all("1234", actor_session_id=third.session["sessionId"]) == 2
    assert service.authenticate(third.token) is None
    assert service.authenticate(fourth.token) is None


def test_failed_pin_attempts_are_rate_limited_and_not_audited_with_pin(tmp_path: Path) -> None:
    clock = MutableClock()
    service = AuthService(tmp_path / "auth.json", clock=clock)
    service.setup("1234", duration="browser-session", custom_seconds=None, user_agent="setup")
    for _ in range(4):
        with pytest.raises(AuthError) as exc:
            service.login("9999", duration="1-hour", custom_seconds=None, user_agent="bad", client_key="loopback")
        assert exc.value.code == "invalid_pin"
    with pytest.raises(AuthError) as fifth:
        service.login("9999", duration="1-hour", custom_seconds=None, user_agent="bad", client_key="loopback")
    assert fifth.value.retry_after == 30
    with pytest.raises(AuthError) as locked:
        service.login("1234", duration="1-hour", custom_seconds=None, user_agent="good", client_key="loopback")
    assert locked.value.code == "rate_limited"
    encoded = json.dumps(service.audit_events(500)).lower()
    assert "9999" not in encoded
    assert "1234" not in encoded
    assert "token" not in encoded

def test_corrupt_auth_store_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(AuthError) as exc:
        AuthService(path)
    assert exc.value.code == "auth_store_corrupt"
