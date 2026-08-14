from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import time
import uuid
from typing import Any, Awaitable, Callable, MutableMapping


_LOGGER_NAME = "droid_web_display.server"
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_DEFAULT_BACKUPS = 5
_REDACTED = "[REDACTED]"

_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b(pin|currentpin|newpin|confirmpin|token|csrftoken|csrf|cookie|authorization)"
    r"(\s*[:=]\s*)([^\s,;&]+)"
)
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[^\s,;&]+")

_ALLOWED_FIELDS = (
    "event",
    "request_id",
    "method",
    "path",
    "status",
    "duration_ms",
    "client",
    "close_code",
    "error_code",
    "error_message",
    "pid",
    "version",
    "url",
    "network_mode",
    "websocket_backend",
    "log_file",
    "reason",
    "restart_requested",
)


def redact_text(value: str) -> str:
    """Redact common authentication secrets from human-readable log text."""

    value = _BEARER_TOKEN.sub(f"Bearer {_REDACTED}", value)
    return _SENSITIVE_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}{_REDACTED}",
        value,
    )


class JsonLineFormatter(logging.Formatter):
    """Write one bounded, machine-readable JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(record.getMessage()),
            "process": record.process,
            "thread": record.threadName,
        }
        for field in _ALLOWED_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                if isinstance(value, Path):
                    value = str(value)
                if isinstance(value, str):
                    value = redact_text(value)
                payload[field] = value
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _coerce_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    value = logging.getLevelName(level.upper())
    if not isinstance(value, int):
        raise ValueError(f"Unsupported log level: {level}")
    return value


def configure_server_logging(
    log_directory: Path,
    *,
    level: str | int = "INFO",
    maximum_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUPS,
) -> tuple[logging.Logger, Path]:
    """Install a bounded JSONL file handler shared by server and library loggers."""

    if maximum_bytes < 64 * 1024:
        raise ValueError("maximum_bytes must be at least 65536")
    if backup_count < 1:
        raise ValueError("backup_count must be at least 1")

    level_value = _coerce_level(level)
    log_directory = log_directory.resolve()
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / "server.log"

    root = logging.getLogger()
    existing = next(
        (
            handler
            for handler in root.handlers
            if getattr(handler, "_dwd_server_log_path", None) == str(log_path)
        ),
        None,
    )
    if existing is None:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=maximum_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,
        )
        handler.setLevel(level_value)
        handler.setFormatter(JsonLineFormatter())
        setattr(handler, "_dwd_server_log_path", str(log_path))
        root.addHandler(handler)
    else:
        existing.setLevel(level_value)

    if root.level == logging.NOTSET or root.level > level_value:
        root.setLevel(level_value)

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level_value)
    logger.info(
        "Server diagnostic logging configured",
        extra={"event": "logging.configured", "log_file": str(log_path)},
    )
    return logger, log_path


def _client_host(scope: MutableMapping[str, Any]) -> str | None:
    client = scope.get("client")
    if isinstance(client, (tuple, list)) and client:
        return str(client[0])
    return None


def _extract_error(body: bytes) -> tuple[str | None, str | None]:
    if not body:
        return None, None
    try:
        value = json.loads(body.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeError):
        return None, None
    if not isinstance(value, dict):
        return None, None
    error = value.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
        return (
            str(code)[:120] if code is not None else None,
            redact_text(str(message))[:500] if message is not None else None,
        )
    detail = value.get("detail")
    if detail is not None:
        return "http_error", redact_text(str(detail))[:500]
    return None, None


class DiagnosticLoggingMiddleware:
    """ASGI middleware for sanitized HTTP/WebSocket lifecycle diagnostics."""

    def __init__(self, app: Callable[..., Awaitable[None]], logger: logging.Logger | None = None) -> None:
        self.app = app
        self.logger = logger or logging.getLogger(_LOGGER_NAME)

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        scope_type = scope.get("type")
        if scope_type == "http":
            await self._http(scope, receive, send)
            return
        if scope_type == "websocket":
            await self._websocket(scope, receive, send)
            return
        await self.app(scope, receive, send)

    async def _http(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        request_id = uuid.uuid4().hex[:16]
        method = str(scope.get("method") or "")
        path = str(scope.get("path") or "/")
        client = _client_host(scope)
        started = time.perf_counter()
        status = 500
        error_body = bytearray()
        raised = False

        async def send_wrapper(message) -> None:  # type: ignore[no-untyped-def]
            nonlocal status
            message_type = message.get("type")
            if message_type == "http.response.start":
                status = int(message.get("status", 500))
                headers = list(message.get("headers", []))
                headers.append((b"x-dwd-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            elif message_type == "http.response.body" and status >= 400:
                body = message.get("body", b"")
                if isinstance(body, bytes) and len(error_body) < 8192:
                    remaining = 8192 - len(error_body)
                    error_body.extend(body[:remaining])
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except BaseException as exc:
            raised = True
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            self.logger.exception(
                "%s %s raised %s",
                method,
                path,
                type(exc).__name__,
                extra={
                    "event": "http.exception",
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status": status,
                    "duration_ms": duration_ms,
                    "client": client,
                    "error_code": type(exc).__name__,
                },
            )
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            error_code, error_message = _extract_error(bytes(error_body))
            if status >= 500:
                level = logging.ERROR
            elif status >= 400:
                level = logging.WARNING
            elif path == "/api/v1/health":
                level = logging.DEBUG
            elif path.startswith("/api/"):
                level = logging.INFO
            else:
                level = logging.DEBUG
            self.logger.log(
                level,
                "%s %s -> %s",
                method,
                path,
                status,
                extra={
                    "event": "http.request",
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status": status,
                    "duration_ms": duration_ms,
                    "client": client,
                    "error_code": error_code,
                    "error_message": error_message,
                    "reason": "exception" if raised else None,
                },
            )

    async def _websocket(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        request_id = uuid.uuid4().hex[:16]
        path = str(scope.get("path") or "/")
        client = _client_host(scope)
        started = time.perf_counter()
        accepted = False
        close_code: int | None = None

        async def receive_wrapper():  # type: ignore[no-untyped-def]
            nonlocal close_code
            message = await receive()
            if message.get("type") == "websocket.disconnect":
                close_code = int(message.get("code", 1000))
            return message

        async def send_wrapper(message) -> None:  # type: ignore[no-untyped-def]
            nonlocal accepted, close_code
            if message.get("type") == "websocket.accept":
                accepted = True
            elif message.get("type") == "websocket.close":
                close_code = int(message.get("code", 1000))
            await send(message)

        self.logger.info(
            "WebSocket connect %s",
            path,
            extra={
                "event": "websocket.connect",
                "request_id": request_id,
                "path": path,
                "client": client,
            },
        )
        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        except BaseException as exc:
            self.logger.exception(
                "WebSocket %s raised %s",
                path,
                type(exc).__name__,
                extra={
                    "event": "websocket.exception",
                    "request_id": request_id,
                    "path": path,
                    "client": client,
                    "close_code": close_code,
                    "error_code": type(exc).__name__,
                },
            )
            raise
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            level = logging.WARNING if (close_code or 1000) >= 4000 else logging.INFO
            self.logger.log(
                level,
                "WebSocket close %s code=%s",
                path,
                close_code,
                extra={
                    "event": "websocket.close",
                    "request_id": request_id,
                    "path": path,
                    "client": client,
                    "close_code": close_code,
                    "duration_ms": duration_ms,
                    "reason": "accepted" if accepted else "rejected",
                },
            )
