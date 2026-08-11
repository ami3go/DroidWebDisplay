from __future__ import annotations

import asyncio

import pytest
from starlette.websockets import WebSocketState

from droid_web_display.errors import SessionConflictError
from droid_web_display.models import ChannelName
from droid_web_display.scrcpy.session import PrefixedStreamReader, ScrcpyChannel
from droid_web_display.websocket.channels import relay_control_websocket, relay_media_websocket


class FakeWriter:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False
        self.written = asyncio.Event()

    def write(self, data: bytes) -> None:
        self.data.extend(data)
        self.written.set()

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class FakeWebSocket:
    def __init__(self) -> None:
        self.client_state = WebSocketState.CONNECTING
        self.sent: list[bytes] = []
        self.received: asyncio.Queue[dict] = asyncio.Queue()
        self.close_code: int | None = None
        self.close_reason: str | None = None

    async def accept(self) -> None:
        self.client_state = WebSocketState.CONNECTED

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(bytes(data))

    async def receive(self) -> dict:
        return await self.received.get()

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.close_code = code
        self.close_reason = reason
        self.client_state = WebSocketState.DISCONNECTED


@pytest.mark.asyncio
async def test_media_websocket_preserves_all_binary_bytes() -> None:
    source = asyncio.StreamReader()
    payload = bytes(range(256)) + b"\x00\xffscrcpy"
    source.feed_data(payload[:31])
    source.feed_data(payload[31:])
    source.feed_eof()
    channel = ScrcpyChannel(ChannelName.VIDEO, PrefixedStreamReader(source), FakeWriter())  # type: ignore[arg-type]
    websocket = FakeWebSocket()

    result = await relay_media_websocket(channel, websocket)

    assert b"".join(websocket.sent) == payload
    assert result.device_to_browser_bytes == len(payload)
    assert channel.bytes_from_device == len(payload)
    assert result.close_reason == "device_eof"


@pytest.mark.asyncio
async def test_control_websocket_relays_both_directions() -> None:
    source = asyncio.StreamReader()
    writer = FakeWriter()
    channel = ScrcpyChannel(ChannelName.CONTROL, PrefixedStreamReader(source), writer)  # type: ignore[arg-type]
    websocket = FakeWebSocket()
    task = asyncio.create_task(relay_control_websocket(channel, websocket))

    browser_payload = b"control\x00\xff"
    await websocket.received.put({"type": "websocket.receive", "bytes": browser_payload})
    await asyncio.wait_for(writer.written.wait(), timeout=1)
    device_payload = b"clipboard-message"
    source.feed_data(device_payload)
    source.feed_eof()

    result = await asyncio.wait_for(task, timeout=1)
    assert bytes(writer.data) == browser_payload
    assert b"".join(websocket.sent) == device_payload
    assert result.browser_to_device_bytes == len(browser_payload)
    assert result.device_to_browser_bytes == len(device_payload)


@pytest.mark.asyncio
async def test_channel_allows_only_one_browser_attachment() -> None:
    source = asyncio.StreamReader()
    channel = ScrcpyChannel(ChannelName.VIDEO, PrefixedStreamReader(source), FakeWriter())  # type: ignore[arg-type]
    await channel.claim("browser-a")
    with pytest.raises(SessionConflictError):
        await channel.claim("browser-b")
    await channel.release("browser-a", reason="test")
    await channel.claim("browser-b")
    assert channel.attached_client == "browser-b"
