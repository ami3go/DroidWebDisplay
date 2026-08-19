from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import copy
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from typing import Any, Callable


AUTH_COOKIE_NAME = "droid_web_display_id"
CSRF_HEADER_NAME = "x-droidwebdisplay-csrf"
PIN_PATTERN = re.compile(r"^[0-9]{4,12}$")
PBKDF2_ITERATIONS = 600_000
SESSION_TOKEN_BYTES = 32
CSRF_TOKEN_BYTES = 24
BROWSER_SESSION_MAX_SECONDS = 24 * 60 * 60
CUSTOM_MIN_SECONDS = 5 * 60
CUSTOM_MAX_SECONDS = 10 * 365 * 24 * 60 * 60
AUDIT_LIMIT = 500
REVOKED_SESSION_LIMIT = 100

TRUST_DURATIONS: dict[str, int | None] = {
    "browser-session": BROWSER_SESSION_MAX_SECONDS,
    "1-hour": 60 * 60,
    "1-day": 24 * 60 * 60,
    "1-week": 7 * 24 * 60 * 60,
    "1-month": 30 * 24 * 60 * 60,
    "1-year": 365 * 24 * 60 * 60,
    "forever": None,
}


class AuthError(RuntimeError):
    def __init__(self, message: str, *, code: str = "auth_error", retry_after: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True)
class SessionGrant:
    token: str
    csrf_token: str
    session: dict[str, Any]
    cookie_max_age: int | None


@dataclass
class _AttemptState:
    failures: int = 0
    first_failure_at: float = 0.0
    locked_until: float = 0.0


class AuthService:
    """PC-local PIN authentication and trusted browser session store.

    The Android phone is not an authentication authority. Session tokens are
    random opaque values; only their SHA-256 digests are stored on disk.
    """

    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time) -> None:
        self.path = path.resolve()
        self.clock = clock
        self._lock = threading.RLock()
        self._attempts: dict[str, _AttemptState] = {}
        self._state = self._load()
        self._cleanup_expired(persist=True)

    @property
    def configured(self) -> bool:
        return isinstance(self._state.get("pin"), dict)

    @staticmethod
    def validate_pin(pin: str) -> str:
        if not PIN_PATTERN.fullmatch(pin):
            raise AuthError("PIN must contain 4 to 12 digits", code="pin_validation")
        return pin

    @staticmethod
    def resolve_duration(choice: str, custom_seconds: int | None = None) -> tuple[int | None, int | None]:
        if choice == "custom":
            if custom_seconds is None or not CUSTOM_MIN_SECONDS <= custom_seconds <= CUSTOM_MAX_SECONDS:
                raise AuthError(
                    "Custom trust duration must be between 5 minutes and 10 years",
                    code="duration_validation",
                )
            return custom_seconds, custom_seconds
        if choice not in TRUST_DURATIONS:
            raise AuthError("Unsupported trust duration", code="duration_validation")
        seconds = TRUST_DURATIONS[choice]
        if choice == "browser-session":
            cookie_max_age = None
        elif choice == "forever":
            cookie_max_age = CUSTOM_MAX_SECONDS
        else:
            cookie_max_age = seconds
        return seconds, cookie_max_age

    def setup(
        self,
        pin: str,
        *,
        duration: str,
        custom_seconds: int | None,
        user_agent: str,
        label: str | None = None,
        client_ip: str | None = None,
        access_mode: str = "local",
    ) -> SessionGrant:
        with self._lock:
            if self.configured:
                raise AuthError("PIN is already configured", code="already_configured")
            pin = self.validate_pin(pin)
            snapshot = copy.deepcopy(self._state)
            self._state["pin"] = self._hash_pin(pin)
            self._audit("pin-configured")
            try:
                grant = self._create_session(
                    duration=duration,
                    custom_seconds=custom_seconds,
                    user_agent=user_agent,
                    label=label,
                    client_ip=client_ip,
                    access_mode=access_mode,
                )
                self._persist()
            except Exception:
                self._state = snapshot
                raise
            return grant

    def login(
        self,
        pin: str,
        *,
        duration: str,
        custom_seconds: int | None,
        user_agent: str,
        client_key: str,
        label: str | None = None,
        client_ip: str | None = None,
        access_mode: str = "local",
    ) -> SessionGrant:
        with self._lock:
            if not self.configured:
                raise AuthError("PIN has not been configured", code="not_configured")
            self._check_lockout(client_key)
            if not self._verify_pin(pin):
                retry_after = self._record_failure(client_key)
                self._audit("login-failed", result="rejected")
                raise AuthError("Invalid PIN", code="invalid_pin", retry_after=retry_after)
            self._attempts.pop(client_key, None)
            grant = self._create_session(
                duration=duration,
                custom_seconds=custom_seconds,
                user_agent=user_agent,
                label=label,
                client_ip=client_ip,
                access_mode=access_mode,
            )
            self._audit("login-success", sessionId=grant.session["sessionId"])
            self._persist()
            return grant

    def authenticate(self, token: str | None, *, touch: bool = True) -> dict[str, Any] | None:
        if not token:
            return None
        digest = self._token_digest(token)
        now = self.clock()
        with self._lock:
            changed = self._cleanup_expired(persist=False)
            for item in self._state.get("sessions", []):
                if hmac.compare_digest(str(item.get("tokenHash", "")), digest):
                    if item.get("revokedAt") is not None:
                        return None
                    expires_at = item.get("expiresAt")
                    if expires_at is not None and now >= float(expires_at):
                        return None
                    if touch and now - float(item.get("lastSeenAt") or 0) >= 60:
                        item["lastSeenAt"] = now
                        changed = True
                    if changed:
                        self._persist()
                    return self._public_session(item)
            if changed:
                self._persist()
        return None

    def csrf_token(self, session_id: str) -> str | None:
        with self._lock:
            item = self._find_session(session_id)
            return str(item.get("csrfToken")) if item is not None else None

    def csrf_valid(self, session_id: str, csrf_token: str | None) -> bool:
        if not csrf_token:
            return False
        with self._lock:
            item = self._find_session(session_id)
            if item is None:
                return False
            return hmac.compare_digest(str(item.get("csrfToken", "")), csrf_token)

    def logout(self, session_id: str) -> None:
        with self._lock:
            item = self._find_session(session_id)
            if item is None:
                return
            item["revokedAt"] = self.clock()
            item["revocationReason"] = "logout"
            self._audit("logout", sessionId=session_id)
            self._persist()

    def list_sessions(self, current_session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._cleanup_expired(persist=True)
            values: list[dict[str, Any]] = []
            for item in self._state.get("sessions", []):
                public = self._public_session(item)
                public["current"] = public["sessionId"] == current_session_id
                values.append(public)
            return sorted(values, key=lambda item: float(item["createdAt"]), reverse=True)

    def revoke(self, session_id: str, *, actor_session_id: str) -> bool:
        with self._lock:
            item = self._find_session(session_id)
            if item is None or item.get("revokedAt") is not None:
                return False
            item["revokedAt"] = self.clock()
            item["revocationReason"] = "individual"
            self._audit("session-revoked", sessionId=session_id, actorSessionId=actor_session_id)
            self._persist()
            return True

    def revoke_all(self, pin: str, *, actor_session_id: str, client_key: str | None = None) -> int:
        with self._lock:
            if not self._verify_pin_guarded(pin, client_key):
                self._audit("global-revocation-rejected", actorSessionId=actor_session_id)
                raise AuthError("Invalid PIN", code="invalid_pin")
            now = self.clock()
            count = 0
            for item in self._state.get("sessions", []):
                if item.get("revokedAt") is None:
                    item["revokedAt"] = now
                    item["revocationReason"] = "global"
                    count += 1
            self._audit("all-sessions-revoked", count=count, actorSessionId=actor_session_id)
            self._persist()
            return count

    def change_pin(self, current_pin: str, new_pin: str, *, actor_session_id: str, client_key: str | None = None) -> None:
        with self._lock:
            if not self._verify_pin_guarded(current_pin, client_key):
                self._audit("pin-change-rejected", actorSessionId=actor_session_id)
                raise AuthError("Invalid current PIN", code="invalid_pin")
            new_pin = self.validate_pin(new_pin)
            self._state["pin"] = self._hash_pin(new_pin)
            now = self.clock()
            for item in self._state.get("sessions", []):
                if item.get("revokedAt") is None:
                    item["revokedAt"] = now
                    item["revocationReason"] = "pin-changed"
            self._audit("pin-changed", actorSessionId=actor_session_id)
            self._persist()

    def audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._state.get("audit", []))[-max(1, min(limit, AUDIT_LIMIT)):][::-1]

    def verify_pin(self, pin: str, *, client_key: str | None = None) -> bool:
        with self._lock:
            return self._verify_pin_guarded(pin, client_key)

    def revoke_all_for_reason(self, reason: str, *, actor_session_id: str | None = None) -> int:
        with self._lock:
            now = self.clock()
            count = 0
            for item in self._state.get("sessions", []):
                if item.get("revokedAt") is None:
                    item["revokedAt"] = now
                    item["revocationReason"] = reason
                    count += 1
            self._audit("all-sessions-revoked", count=count, reason=reason, actorSessionId=actor_session_id)
            self._persist()
            return count

    def audit_event(self, event: str, **details: Any) -> None:
        with self._lock:
            self._audit(event, **details)
            self._persist()

    def reset(self) -> None:
        with self._lock:
            self._state = self._empty_state()
            if self.path.exists():
                self.path.unlink()

    def _create_session(
        self,
        *,
        duration: str,
        custom_seconds: int | None,
        user_agent: str,
        label: str | None,
        client_ip: str | None,
        access_mode: str,
    ) -> SessionGrant:
        seconds, cookie_max_age = self.resolve_duration(duration, custom_seconds)
        now = self.clock()
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        csrf_token = secrets.token_urlsafe(CSRF_TOKEN_BYTES)
        session_id = secrets.token_urlsafe(12)
        cleaned_label = self._session_label(label, user_agent)
        item = {
            "sessionId": session_id,
            "tokenHash": self._token_digest(token),
            "csrfToken": csrf_token,
            "createdAt": now,
            "lastSeenAt": now,
            "expiresAt": None if seconds is None else now + seconds,
            "duration": duration,
            "customSeconds": custom_seconds if duration == "custom" else None,
            "label": cleaned_label,
            "userAgent": user_agent[:240],
            "clientIp": client_ip,
            "accessMode": access_mode,
            "revokedAt": None,
            "revocationReason": None,
        }
        self._state.setdefault("sessions", []).append(item)
        self._audit("session-created", sessionId=session_id, duration=duration)
        return SessionGrant(
            token=token,
            csrf_token=csrf_token,
            session=self._public_session(item),
            cookie_max_age=cookie_max_age,
        )

    def _check_lockout(self, client_key: str) -> None:
        state = self._attempts.get(client_key)
        if state is None:
            return
        now = self.clock()
        if state.locked_until > now:
            retry = max(1, int(state.locked_until - now + 0.999))
            raise AuthError("Too many failed attempts", code="rate_limited", retry_after=retry)
        if now - state.first_failure_at > 300:
            self._attempts.pop(client_key, None)

    def _record_failure(self, client_key: str) -> int | None:
        now = self.clock()
        state = self._attempts.setdefault(client_key, _AttemptState())
        if state.failures == 0 or now - state.first_failure_at > 300:
            state.failures = 0
            state.first_failure_at = now
        state.failures += 1
        if state.failures >= 5:
            lock_seconds = min(300, 30 * (2 ** min(state.failures - 5, 3)))
            state.locked_until = now + lock_seconds
            return lock_seconds
        return None

    def _hash_pin(self, pin: str) -> dict[str, Any]:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32)
        return {
            "algorithm": "pbkdf2-hmac-sha256",
            "iterations": PBKDF2_ITERATIONS,
            "salt": base64.b64encode(salt).decode("ascii"),
            "hash": base64.b64encode(digest).decode("ascii"),
        }

    def _verify_pin(self, pin: str) -> bool:
        record = self._state.get("pin")
        if not isinstance(record, dict):
            return False
        try:
            salt = base64.b64decode(str(record["salt"]), validate=True)
            expected = base64.b64decode(str(record["hash"]), validate=True)
            iterations = int(record["iterations"])
        except (KeyError, TypeError, ValueError):
            return False
        actual = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, iterations, dklen=len(expected))
        return hmac.compare_digest(actual, expected)

    def _verify_pin_guarded(self, pin: str, client_key: str | None) -> bool:
        """Verify a PIN under the same lockout that protects login().

        Every PIN check reachable from the API must be rate limited, otherwise
        an already-authenticated client can use it as an unthrottled oracle.
        """
        if client_key is None:
            return self._verify_pin(pin)
        self._check_lockout(client_key)
        if self._verify_pin(pin):
            self._attempts.pop(client_key, None)
            return True
        self._record_failure(client_key)
        return False

    @staticmethod
    def _token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _find_session(self, session_id: str) -> dict[str, Any] | None:
        return next((item for item in self._state.get("sessions", []) if item.get("sessionId") == session_id), None)

    def _prune_revoked_sessions(self) -> bool:
        sessions = list(self._state.get("sessions", []))
        revoked = [item for item in sessions if item.get("revokedAt") is not None]
        if len(revoked) <= REVOKED_SESSION_LIMIT:
            return False
        newest = sorted(
            revoked,
            key=lambda item: float(item.get("revokedAt") or item.get("createdAt") or 0),
            reverse=True,
        )[:REVOKED_SESSION_LIMIT]
        keep = {id(item) for item in newest}
        self._state["sessions"] = [
            item
            for item in sessions
            if item.get("revokedAt") is None or id(item) in keep
        ]
        return True

    def _cleanup_expired(self, *, persist: bool) -> bool:
        now = self.clock()
        changed = False
        for item in self._state.get("sessions", []):
            if item.get("revokedAt") is not None:
                continue
            expires_at = item.get("expiresAt")
            if expires_at is not None and now >= float(expires_at):
                item["revokedAt"] = now
                item["revocationReason"] = "expired"
                self._audit("session-expired", sessionId=item.get("sessionId"))
                changed = True
        changed = self._prune_revoked_sessions() or changed
        if changed and persist:
            self._persist()
        return changed

    def _audit(self, event: str, **details: Any) -> None:
        sanitized = {key: value for key, value in details.items() if "pin" not in key.lower() and "token" not in key.lower()}
        self._state.setdefault("audit", []).append({
            "timestamp": self.clock(),
            "event": event,
            **sanitized,
        })
        self._state["audit"] = self._state["audit"][-AUDIT_LIMIT:]

    @staticmethod
    def _session_label(label: str | None, user_agent: str) -> str:
        if label:
            cleaned = " ".join(label.strip().split())[:80]
            if cleaned:
                return cleaned
        ua = user_agent.lower()
        browser = "Firefox" if "firefox" in ua else ("Edge" if "edg/" in ua else ("Chromium" if "chrome" in ua else "Browser"))
        platform = "Windows" if "windows" in ua else ("Linux" if "linux" in ua else ("Android" if "android" in ua else "PC"))
        return f"{browser} on {platform}"

    @staticmethod
    def _public_session(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "sessionId": item.get("sessionId"),
            "createdAt": item.get("createdAt"),
            "lastSeenAt": item.get("lastSeenAt"),
            "expiresAt": item.get("expiresAt"),
            "duration": item.get("duration"),
            "customSeconds": item.get("customSeconds"),
            "label": item.get("label"),
            "userAgent": item.get("userAgent"),
            "clientIp": item.get("clientIp"),
            "accessMode": item.get("accessMode", "local"),
            "revokedAt": item.get("revokedAt"),
            "revocationReason": item.get("revocationReason"),
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._empty_state()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthError(
                f"Authentication store is unreadable or corrupt: {self.path}",
                code="auth_store_corrupt",
            ) from exc
        if value.get("schemaVersion") != 1:
            raise AuthError(
                f"Unsupported authentication store schema: {self.path}",
                code="auth_store_corrupt",
            )
        if value.get("pin") is not None and not isinstance(value.get("pin"), dict):
            raise AuthError(
                f"Authentication store PIN record is invalid: {self.path}",
                code="auth_store_corrupt",
            )
        if not isinstance(value.get("sessions", []), list) or not isinstance(value.get("audit", []), list):
            raise AuthError(
                f"Authentication store structure is invalid: {self.path}",
                code="auth_store_corrupt",
            )
        value.setdefault("sessions", [])
        value.setdefault("audit", [])
        return value

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {"schemaVersion": 1, "pin": None, "sessions": [], "audit": []}

    def _persist(self) -> None:
        self._prune_revoked_sessions()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(self._state, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        temporary.write_text(payload, encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass


def utc_iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
