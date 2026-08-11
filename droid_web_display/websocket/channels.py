from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Protocol

from starlette.websockets import WebSocketDisconnect, WebSocketState

from droid_web_display.scrcpy.session import ScrcpyChannel


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


async def relay_media_websocket(
    channel: ScrcpyChannel,
    websocket: BinaryWebSocket,
    *,
    chunk_size: int = 64 * 1024,
) -> WebSocketRelayResult:
    """Send a scrcpy media channel to the browser without changing any byte."""

    result = WebSocketRelayResult()
    await websocket.accept()
    try:
        while True:
            data = await channel.reader.read(chunk_size)
            if not data:
                result.close_reason = "device_eof"
                return result
            await websocket.send_bytes(data)
            channel.bytes_from_device += len(data)
            result.device_to_browser_bytes += len(data)
    except WebSocketDisconnect:
        result.close_reason = "browser_disconnected"
        return result
    except (ConnectionError, RuntimeError):
        result.close_reason = "transport_error"
        return result
    finally:
        await _safe_close(websocket)


async def relay_control_websocket(
    channel: ScrcpyChannel,
    websocket: BinaryWebSocket,
    *,
    chunk_size: int = 64 * 1024,
    maximum_browser_message_size: int = 256 * 1024,
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
