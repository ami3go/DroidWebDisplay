from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocketState

from droid_web_display.auth import AUTH_COOKIE_NAME
from droid_web_display.models import ChannelName
from droid_web_display.websocket.channels import _websocket_authorized, relay_control_websocket


class BlockingReader:
    async def read(self, _size: int) -> bytes:
        await asyncio.Event().wait()
        return b""


class DummyWriter:
    def write(self, _data: bytes) -> None:
        pass

    async def drain(self) -> None:
        pass


class DummyChannel:
    name = ChannelName.CONTROL
    reader = BlockingReader()
    writer = DummyWriter()
    bytes_from_device = 0
    bytes_to_device = 0


class DummyAuth:
    def __init__(self, valid: bool) -> None:
        self.valid = valid

    def authenticate(self, token: str | None, *, touch: bool = True):
        assert touch is False
        return {"sessionId": "browser"} if self.valid and token == "token" else None


class DummyWebSocket:
    def __init__(self, *, auth: DummyAuth | None = None) -> None:
        self.client_state = WebSocketState.CONNECTING
        self.closed: tuple[int, str | None] | None = None
        self.cookies = {AUTH_COOKIE_NAME: "token"}
        if auth is not None:
            self.app = SimpleNamespace(
                state=SimpleNamespace(
                    container=SimpleNamespace(
                        config=SimpleNamespace(authentication_required=True),
                        auth=auth,
                    )
                )
            )

    async def accept(self) -> None:
        self.client_state = WebSocketState.CONNECTED

    async def send_bytes(self, _data: bytes) -> None:
        pass

    async def receive(self) -> dict:
        await asyncio.Event().wait()
        return {"type": "websocket.disconnect"}

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed = (code, reason)
        self.client_state = WebSocketState.DISCONNECTED


def test_websocket_authorization_uses_live_auth_state() -> None:
    auth = DummyAuth(True)
    websocket = DummyWebSocket(auth=auth)
    assert _websocket_authorized(websocket) is True
    auth.valid = False
    assert _websocket_authorized(websocket) is False


@pytest.mark.asyncio
async def test_control_relay_closes_after_browser_session_revocation() -> None:
    auth = DummyAuth(True)
    websocket = DummyWebSocket(auth=auth)
    task = asyncio.create_task(
        relay_control_websocket(
            DummyChannel(),  # type: ignore[arg-type]
            websocket,  # type: ignore[arg-type]
            authorization_interval=0.01,
        )
    )
    await asyncio.sleep(0.02)
    auth.valid = False
    result = await asyncio.wait_for(task, timeout=0.5)

    assert result.close_reason == "authentication_revoked"
    assert websocket.closed == (4401, "browser session expired or revoked")
