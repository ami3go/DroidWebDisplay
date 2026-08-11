from __future__ import annotations

import json
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from droid_web_display import RELEASE_PHASE


_HTTP_PHASE_PATHS = {
    "/api/v1/health",
    "/api/v1/version",
    "/api/v1/diagnostics",
}
_WS_PHASE_PATHS = {"/ws/v1/events"}


def _rewrite_payload(value: Any) -> tuple[Any, bool]:
    if isinstance(value, dict) and "phase" in value and value.get("phase") != RELEASE_PHASE:
        return {**value, "phase": RELEASE_PHASE}, True
    return value, False


def _rewrite_json_bytes(data: bytes) -> tuple[bytes, bool]:
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return data, False
    value, changed = _rewrite_payload(value)
    if not changed:
        return data, False
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), True


class ReleaseMetadataMiddleware:
    """Expose canonical release metadata without duplicating version constants.

    Phase metadata historically lived as endpoint-local literals in the large
    API module. This middleware is installed by the public package factory and
    makes the canonical ``RELEASE_PHASE`` authoritative for HTTP diagnostics
    and the event WebSocket while that module is split in a later refactor.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        path = scope.get("path", "")
        if scope_type == "http" and path in _HTTP_PHASE_PATHS:
            await self._http(scope, receive, send)
            return
        if scope_type == "websocket" and path in _WS_PHASE_PATHS:
            await self._websocket(scope, receive, send)
            return
        await self.app(scope, receive, send)

    async def _http(self, scope: Scope, receive: Receive, send: Send) -> None:
        start_message: Message | None = None
        body_parts: list[bytes] = []

        async def intercept(message: Message) -> None:
            nonlocal start_message
            message_type = message["type"]
            if message_type == "http.response.start":
                start_message = message
                return
            if message_type != "http.response.body":
                if start_message is not None:
                    await send(start_message)
                    start_message = None
                await send(message)
                return

            body_parts.append(message.get("body", b""))
            if message.get("more_body", False):
                return

            original = b"".join(body_parts)
            rewritten, changed = _rewrite_json_bytes(original)
            if start_message is not None:
                start = start_message
                if changed:
                    headers = [
                        (name, value)
                        for name, value in start.get("headers", [])
                        if name.lower() != b"content-length"
                    ]
                    headers.append((b"content-length", str(len(rewritten)).encode("ascii")))
                    start = {**start, "headers": headers}
                await send(start)
                start_message = None
            await send({**message, "body": rewritten, "more_body": False})

        await self.app(scope, receive, intercept)

    async def _websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def intercept(message: Message) -> None:
            if message["type"] != "websocket.send":
                await send(message)
                return

            if message.get("text") is not None:
                try:
                    value = json.loads(message["text"])
                except json.JSONDecodeError:
                    await send(message)
                    return
                value, changed = _rewrite_payload(value)
                if changed:
                    message = {
                        **message,
                        "text": json.dumps(value, separators=(",", ":"), ensure_ascii=False),
                    }
            elif message.get("bytes") is not None:
                rewritten, changed = _rewrite_json_bytes(message["bytes"])
                if changed:
                    message = {**message, "bytes": rewritten}
            await send(message)

        await self.app(scope, receive, intercept)


def install_release_metadata(app: Any) -> Any:
    app.add_middleware(ReleaseMetadataMiddleware)
    return app
