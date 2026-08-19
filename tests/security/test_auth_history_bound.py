from __future__ import annotations

import json
from pathlib import Path

from droid_web_display.auth import AuthService, REVOKED_SESSION_LIMIT


def session(index: int, *, revoked: bool) -> dict:
    return {
        "sessionId": f"session-{index}",
        "tokenHash": f"hash-{index}",
        "csrfToken": f"csrf-{index}",
        "createdAt": float(index),
        "lastSeenAt": float(index),
        "expiresAt": None,
        "duration": "forever",
        "customSeconds": None,
        "label": f"Session {index}",
        "userAgent": "test",
        "clientIp": "127.0.0.1",
        "accessMode": "local",
        "revokedAt": float(index) if revoked else None,
        "revocationReason": "test" if revoked else None,
    }


def test_persistence_keeps_all_active_and_only_recent_revoked_sessions(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    service = AuthService(path)
    active = [session(-1, revoked=False), session(-2, revoked=False)]
    revoked = [session(index, revoked=True) for index in range(REVOKED_SESSION_LIMIT + 25)]
    service._state["sessions"] = [*active, *revoked]

    service._persist()

    persisted = json.loads(path.read_text(encoding="utf-8"))["sessions"]
    active_ids = {item["sessionId"] for item in persisted if item["revokedAt"] is None}
    revoked_ids = {item["sessionId"] for item in persisted if item["revokedAt"] is not None}
    assert active_ids == {"session--1", "session--2"}
    assert len(revoked_ids) == REVOKED_SESSION_LIMIT
    assert "session-0" not in revoked_ids
    assert f"session-{REVOKED_SESSION_LIMIT + 24}" in revoked_ids
