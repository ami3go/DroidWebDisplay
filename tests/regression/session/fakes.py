from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Sequence

from droid_web_display.models import AndroidDevice


class FakeProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        self.terminated = False
        self.killed = False
        self._done = asyncio.Event()

    async def wait(self) -> int:
        await self._done.wait()
        return int(self.returncode or 0)

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self._done.set()

    def kill(self) -> None:
        self.killed = True
        self.exit(-9)

    def exit(self, returncode: int) -> None:
        self.returncode = returncode
        self.stdout.feed_eof()
        self.stderr.feed_eof()
        self._done.set()


class FakeAdb:
    def __init__(self, devices: list[AndroidDevice] | None = None) -> None:
        self.devices = devices or []
        self.pushed: list[tuple[str, Path, str]] = []
        self.forwards: list[tuple[str, int, str]] = []
        self.removed: list[tuple[str, int]] = []
        self.server_args: list[tuple[str, tuple[str, ...]]] = []
        self.processes: list[FakeProcess] = []
        self.forward_server: asyncio.AbstractServer | None = None
        self.connections = 0
        self.connection_payloads = [
            b"\x00" + b"D" * 64 + b"VIDEO-PAYLOAD",
            b"CONTROL-PAYLOAD",
            b"AUDIO-PAYLOAD",
        ]

    async def list_devices(self, *, enrich: bool = False) -> list[AndroidDevice]:
        return list(self.devices)

    async def get_state(self, serial: str) -> str:
        item = next((device for device in self.devices if device.serial == serial), None)
        return item.state if item else "disconnected"

    async def push(self, serial: str, local: Path, remote: str) -> None:
        self.pushed.append((serial, local, remote))

    async def create_forward(self, serial: str, local_port: int, socket_name: str) -> None:
        self.forwards.append((serial, local_port, socket_name))

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            index = self.connections
            self.connections += 1
            payload = self.connection_payloads[index] if index < len(self.connection_payloads) else b"EXTRA"
            writer.write(payload)
            await writer.drain()
            try:
                await reader.read()
            finally:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

        self.forward_server = await asyncio.start_server(handle, "127.0.0.1", local_port)

    async def remove_forward(self, serial: str, local_port: int) -> None:
        self.removed.append((serial, local_port))
        if self.forward_server:
            self.forward_server.close()
            await self.forward_server.wait_closed()
            self.forward_server = None

    async def spawn_server(self, serial: str, server_args: Sequence[str]) -> FakeProcess:
        self.server_args.append((serial, tuple(server_args)))
        process = FakeProcess()
        self.processes.append(process)
        return process

    async def version(self) -> str:
        return "Android Debug Bridge version 1.0.41"
