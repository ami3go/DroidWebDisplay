from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from droid_web_display.diagnostics import DiagnosticLoggingMiddleware, configure_server_logging


def _flush_and_detach(log_path: Path) -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_dwd_server_log_path", None) == str(log_path):
            handler.flush()
            handler.close()
            root.removeHandler(handler)


def _read_events(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line]


def test_server_log_is_jsonl_and_redacts_sensitive_values(tmp_path: Path) -> None:
    logger, log_path = configure_server_logging(tmp_path, level="DEBUG")
    logger.warning(
        "pin=1234 token=secret-token Authorization: Bearer abcdef Cookie: dwd_session=opaque",
        extra={
            "event": "test.redaction",
            "error_message": "csrfToken=csrf-secret currentPin=9876",
        },
    )
    _flush_and_detach(log_path)

    raw = log_path.read_text(encoding="utf-8")
    assert "1234" not in raw
    assert "9876" not in raw
    assert "secret-token" not in raw
    assert "abcdef" not in raw
    assert "opaque" not in raw
    assert "csrf-secret" not in raw
    assert "[REDACTED]" in raw

    event = next(item for item in _read_events(log_path) if item.get("event") == "test.redaction")
    assert event["level"] == "WARNING"
    assert event["logger"] == "droid_web_display.server"


def test_http_diagnostics_drop_query_string_and_extract_error_code(tmp_path: Path) -> None:
    logger, log_path = configure_server_logging(tmp_path, level="DEBUG")
    sent: list[dict] = []

    async def app(scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        assert scope["query_string"] == b"pin=2468&token=query-secret"
        await send(
            {
                "type": "http.response.start",
                "status": 422,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(
                    {"error": {"code": "validation_failed", "message": "pin=2468 token=body-secret"}}
                ).encode("utf-8"),
            }
        )

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/test",
        "raw_path": b"/api/v1/test",
        "query_string": b"pin=2468&token=query-secret",
        "headers": [],
        "client": ("127.0.0.1", 54321),
        "server": ("127.0.0.1", 8765),
    }

    asyncio.run(DiagnosticLoggingMiddleware(app, logger=logger)(scope, receive, send))
    _flush_and_detach(log_path)

    raw = log_path.read_text(encoding="utf-8")
    assert "query-secret" not in raw
    assert "body-secret" not in raw
    assert "2468" not in raw

    events = _read_events(log_path)
    request = next(item for item in events if item.get("event") == "http.request")
    assert request["method"] == "POST"
    assert request["path"] == "/api/v1/test"
    assert request["status"] == 422
    assert request["error_code"] == "validation_failed"
    assert "query" not in request

    response_start = next(item for item in sent if item["type"] == "http.response.start")
    headers = dict(response_start["headers"])
    assert b"x-dwd-request-id" in headers


def test_websocket_lifecycle_is_logged_without_query_string(tmp_path: Path) -> None:
    logger, log_path = configure_server_logging(tmp_path, level="INFO")
    sent: list[dict] = []

    async def app(scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        await send({"type": "websocket.accept"})
        await send({"type": "websocket.close", "code": 4404, "reason": "session not found"})

    async def receive() -> dict:
        return {"type": "websocket.connect"}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        "type": "websocket",
        "scheme": "ws",
        "path": "/ws/v1/sessions/example/video",
        "raw_path": b"/ws/v1/sessions/example/video",
        "query_string": b"clientId=should-not-be-logged",
        "headers": [],
        "client": ("127.0.0.1", 54321),
        "server": ("127.0.0.1", 8765),
        "subprotocols": [],
    }

    asyncio.run(DiagnosticLoggingMiddleware(app, logger=logger)(scope, receive, send))
    _flush_and_detach(log_path)

    raw = log_path.read_text(encoding="utf-8")
    assert "should-not-be-logged" not in raw
    events = _read_events(log_path)
    assert any(item.get("event") == "websocket.connect" for item in events)
    closed = next(item for item in events if item.get("event") == "websocket.close")
    assert closed["close_code"] == 4404
    assert closed["reason"] == "accepted"
