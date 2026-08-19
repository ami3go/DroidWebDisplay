from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Callable, Protocol

from starlette.websockets import WebSocketDisconnect, WebSocketState

from droid_web_display.auth import AUTH_COOKIE_NAME
from droid_web_display.scrcpy.session import ScrcpyChannel


AuthorizationCheck = Callable[[], bool]


class BinaryWebSocket(Protocol):
    client_state: WebSocketState

    async def accept(self) -> None: ...
    async def send_bytes(self, data: bytes) -> None: ...
    async def receive(self) -> dict: ...
    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


@dataclass
class WebSocketRelayResult:
    device_to_browser_bytes: int = 0
    browser_to_device_bytes: int = 0
    close_reason: str = "completed"


async def _safe_close(websocket: BinaryWebSocket, *, code: int = 1000, reason: str = "") -> None:
    if websocket.client_state == WebSocketState.DISCONNECTED:
        return
    with contextlib.suppress(RuntimeError, WebSocketDisconnect):
        await websocket.close(code=code, reason=reason)


def _websocket_authorized(websocket: BinaryWebSocket) -> bool:
    """Revalidate the browser trust session for an already-open relay.

    The HTTP/WebSocket handshake validates authentication once, but revocation,
    PIN changes and expiry may happen while a scrcpy relay is still open.  A
    real Starlette ``WebSocket`` exposes ``app`` and ``cookies``; test doubles
    that do not expose those attributes are treated as transport-only and keep
    the historical relay behaviour.
    """

    app = getattr(websocket, "app", None)
    state = getattr(app, "state", None)
    container = getattr(state, "container", None)
    if container is None:
        return True

    config = getattr(container, "config", None)
    if config is None or not getattr(config, "authentication_required", False):
        return True

    auth = getattr(container, "auth", None)
    cookies = getattr(websocket, "cookies", None)
    if auth is None or cookies is None:
        return False
    token = cookies.get(AUTH_COOKIE_NAME)
    return auth.authenticate(token, touch=False) is not None


async def _watch_authorization(
    websocket: BinaryWebSocket,
    authorization_check: AuthorizationCheck | None,
    *,
    interval: float,
) -> str:
    check = authorization_check or (lambda: _websocket_authorized(websocket))
    while True:
        await asyncio.sleep(interval)
        try:
            allowed = check()
        except Exception:
            allowed = False
        if allowed:
            continue
        await _safe_close(websocket, code=4401, reason="browser session expired or revoked")
        return "authentication_revoked"


async def relay_media_websocket(
    channel: ScrcpyChannel,
    websocket: BinaryWebSocket,
    *,
    chunk_size: int = 64 * 1024,
    authorization_check: AuthorizationCheck | None = None,
    authorization_interval: float = 0.5,
) -> WebSocketRelayResult:
    """Send a scrcpy media channel to the browser without changing any byte."""

    result = WebSocketRelayResult()
    await websocket.accept()

    async def device_to_browser() -> str:
        while True:
            data = await channel.reader.read(chunk_size)
            if not data:
                return "device_eof"
            await websocket.send_bytes(data)
            channel.bytes_from_device += len(data)
            result.device_to_browser_bytes += len(data)

    tasks = {
        asyncio.create_task(device_to_browser(), name=f"{channel.name.value}-device-to-browser"),
        asyncio.create_task(
            _watch_authorization(websocket, authorization_check, interval=authorization_interval),
            name=f"{channel.name.value}-authorization-watch",
        ),
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        reasons: list[str] = []
        for task in done:
            try:
                reasons.append(task.result())
            except WebSocketDisconnect:
                reasons.append("browser_disconnected")
            except (ConnectionError, RuntimeError):
                reasons.append("transport_error")
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        result.close_reason = reasons[0] if reasons else "channel_closed"
        return result
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await _safe_close(websocket)


async def relay_control_websocket(
    channel: ScrcpyChannel,
    websocket: BinaryWebSocket,
    *,
    chunk_size: int = 64 * 1024,
    maximum_browser_message_size: int = 256 * 1024,
    authorization_check: AuthorizationCheck | None = None,
    authorization_interval: float = 0.5,
) -> WebSocketRelayResult:
    """Relay scrcpy control bytes in both directions without protocol parsing."""

    result = WebSocketRelayResult()
    await websocket.accept()

    async def device_to_browser() -> str:
        while True:
            data = await channel.reader.read(chunk_size)
            if not data:
                return "device_eof"
            await websocket.send_bytes(data)
            channel.bytes_from_device += len(data)
            result.device_to_browser_bytes += len(data)

    async def browser_to_device() -> str:
        while True:
            message = await websocket.receive()
            message_type = message.get("type")
            if message_type == "websocket.disconnect":
                return "browser_disconnected"
            data = message.get("bytes")
            if data is None:
                await _safe_close(websocket, code=1003, reason="binary frames required")
                return "non_binary_message"
            if len(data) > maximum_browser_message_size:
                await _safe_close(websocket, code=1009, reason="control frame too large")
                return "message_too_large"
            channel.writer.write(data)
            await channel.writer.drain()
            channel.bytes_to_device += len(data)
            result.browser_to_device_bytes += len(data)

    tasks = {
        asyncio.create_task(device_to_browser(), name=f"{channel.name.value}-device-to-browser"),
        asyncio.create_task(browser_to_device(), name=f"{channel.name.value}-browser-to-device"),
        asyncio.create_task(
            _watch_authorization(websocket, authorization_check, interval=authorization_interval),
            name=f"{channel.name.value}-authorization-watch",
        ),
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        reasons: list[str] = []
        for task in done:
            try:
                reasons.append(task.result())
            except WebSocketDisconnect:
                reasons.append("browser_disconnected")
            except (ConnectionError, RuntimeError):
                reasons.append("transport_error")
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        result.close_reason = reasons[0] if reasons else "channel_closed"
        return result
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await _safe_close(websocket)
