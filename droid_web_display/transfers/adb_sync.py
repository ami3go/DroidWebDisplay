from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
import struct
import time
from typing import AsyncIterator, Awaitable, Callable

from droid_web_display.errors import AdbSyncError, TransferCancelledError

ProgressCallback = Callable[[int, int | None], Awaitable[None] | None]


@dataclass(frozen=True)
class AdbSyncStat:
    mode: int
    size: int
    modified_at: int

    @property
    def exists(self) -> bool:
        return self.mode != 0

    @property
    def is_directory(self) -> bool:
        return (self.mode & 0o170000) == 0o040000


@dataclass(frozen=True)
class AdbSyncEntry:
    name: str
    mode: int
    size: int
    modified_at: int

    @property
    def is_directory(self) -> bool:
        return (self.mode & 0o170000) == 0o040000


class AdbSyncClient:
    """Structured ADB Sync v1 client.

    This client talks to the local ADB server directly. It does not invoke or
    parse the human-readable output of ``adb push`` or ``adb pull``.
    """

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 5037,
        timeout: float = 30.0,
        chunk_size: int = 64 * 1024,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.chunk_size = min(max(chunk_size, 4096), 64 * 1024)

    @asynccontextmanager
    async def connection(self, serial: str) -> AsyncIterator[tuple[asyncio.StreamReader, asyncio.StreamWriter]]:
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), self.timeout)
        except (OSError, asyncio.TimeoutError) as exc:
            raise AdbSyncError(
                f"Unable to connect to ADB server at {self.host}:{self.port}: {exc}",
                details={"host": self.host, "port": self.port},
            ) from exc
        try:
            await self._host_request(reader, writer, f"host:transport:{serial}")
            await self._host_request(reader, writer, "sync:")
            yield reader, writer
        finally:
            writer.close()
            try:
                # Bounded: a peer that has stopped reading never acknowledges
                # the close, and an unbounded wait here would swallow the very
                # timeout that ended the transfer.
                await asyncio.wait_for(writer.wait_closed(), self.timeout)
            except (ConnectionError, OSError, asyncio.TimeoutError):
                pass

    async def list(self, serial: str, remote_path: str) -> list[AdbSyncEntry]:
        async with self.connection(serial) as (reader, writer):
            await self._send_sync_request(writer, b"LIST", remote_path.encode("utf-8"))
            result: list[AdbSyncEntry] = []
            while True:
                command = await self._read_exactly(reader, 4)
                if command == b"DENT":
                    mode, size, modified_at, name_length = struct.unpack("<IIII", await self._read_exactly(reader, 16))
                    name = (await self._read_exactly(reader, name_length)).decode("utf-8", errors="replace")
                    if name not in {".", ".."}:
                        result.append(AdbSyncEntry(name, mode, size, modified_at))
                    continue
                if command == b"DONE":
                    # LIST DONE uses the same trailing fields as DENT, all zero.
                    await self._read_exactly(reader, 16)
                    return result
                if command == b"FAIL":
                    raise await self._read_sync_failure(reader)
                raise AdbSyncError("Unexpected ADB Sync LIST response", details={"command": command.decode("ascii", "replace")})

    async def stat(self, serial: str, remote_path: str) -> AdbSyncStat:
        async with self.connection(serial) as (reader, writer):
            await self._send_sync_request(writer, b"STAT", remote_path.encode("utf-8"))
            command = await self._read_exactly(reader, 4)
            if command == b"FAIL":
                raise await self._read_sync_failure(reader)
            if command != b"STAT":
                raise AdbSyncError("Unexpected ADB Sync STAT response", details={"command": command.decode("ascii", "replace")})
            mode, size, modified_at = struct.unpack("<III", await self._read_exactly(reader, 12))
            return AdbSyncStat(mode, size, modified_at)

    async def pull(
        self,
        serial: str,
        remote_path: str,
        local_path: Path,
        *,
        progress: ProgressCallback | None = None,
    ) -> int:
        stat = await self.stat(serial, remote_path)
        if not stat.exists or stat.is_directory:
            raise AdbSyncError("Remote source is not a regular file", details={"path": remote_path, "mode": stat.mode})
        local_path.parent.mkdir(parents=True, exist_ok=True)
        transferred = 0
        try:
            async with self.connection(serial) as (reader, writer):
                await self._send_sync_request(writer, b"RECV", remote_path.encode("utf-8"))
                with local_path.open("wb") as output:
                    while True:
                        command = await self._read_exactly(reader, 4)
                        if command == b"DATA":
                            length = struct.unpack("<I", await self._read_exactly(reader, 4))[0]
                            if length > 64 * 1024:
                                raise AdbSyncError("ADB Sync DATA chunk exceeds protocol maximum", details={"length": length})
                            data = await self._read_exactly(reader, length)
                            output.write(data)
                            transferred += len(data)
                            await self._notify(progress, transferred, stat.size)
                            continue
                        if command == b"DONE":
                            await self._read_exactly(reader, 4)
                            break
                        if command == b"FAIL":
                            raise await self._read_sync_failure(reader)
                        raise AdbSyncError("Unexpected ADB Sync RECV response", details={"command": command.decode("ascii", "replace")})
            if transferred != stat.size:
                raise AdbSyncError(
                    "Downloaded size does not match remote STAT size",
                    details={"expected": stat.size, "actual": transferred, "path": remote_path},
                )
            return transferred
        except asyncio.CancelledError as exc:
            raise TransferCancelledError("download cancelled", details={"path": remote_path}) from exc

    async def push(
        self,
        serial: str,
        local_path: Path,
        remote_path: str,
        *,
        progress: ProgressCallback | None = None,
        mode: int = 0o100664,
    ) -> int:
        total = local_path.stat().st_size
        transferred = 0
        send_spec = f"{remote_path},{mode}".encode("utf-8")
        try:
            async with self.connection(serial) as (reader, writer):
                await self._send_sync_request(writer, b"SEND", send_spec)
                with local_path.open("rb") as source:
                    while chunk := source.read(self.chunk_size):
                        writer.write(b"DATA" + struct.pack("<I", len(chunk)) + chunk)
                        await self._drain(writer)
                        transferred += len(chunk)
                        await self._notify(progress, transferred, total)
                writer.write(b"DONE" + struct.pack("<I", int(time.time())))
                await self._drain(writer)
                command = await self._read_exactly(reader, 4)
                status = struct.unpack("<I", await self._read_exactly(reader, 4))[0]
                if command == b"FAIL":
                    message = (await self._read_exactly(reader, status)).decode("utf-8", errors="replace")
                    raise AdbSyncError("ADB Sync SEND failed", details={"message": message, "path": remote_path})
                if command != b"OKAY":
                    raise AdbSyncError("Unexpected ADB Sync SEND response", details={"command": command.decode("ascii", "replace")})
            return transferred
        except asyncio.CancelledError as exc:
            raise TransferCancelledError("upload cancelled", details={"path": remote_path}) from exc

    async def _host_request(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, service: str) -> None:
        payload = service.encode("utf-8")
        writer.write(f"{len(payload):04X}".encode("ascii") + payload)
        await self._drain(writer)
        status = await self._read_exactly(reader, 4)
        if status == b"OKAY":
            return
        if status == b"FAIL":
            raw_length = await self._read_exactly(reader, 4)
            try:
                length = int(raw_length.decode("ascii"), 16)
            except ValueError as exc:
                raise AdbSyncError("Invalid ADB host failure length", details={"value": raw_length.hex()}) from exc
            message = (await self._read_exactly(reader, length)).decode("utf-8", errors="replace")
            raise AdbSyncError("ADB host service failed", details={"service": service, "message": message})
        raise AdbSyncError("Unexpected ADB host response", details={"service": service, "status": status.hex()})

    async def _send_sync_request(self, writer: asyncio.StreamWriter, command: bytes, payload: bytes) -> None:
        if len(command) != 4:
            raise ValueError("ADB Sync command must be four bytes")
        writer.write(command + struct.pack("<I", len(payload)) + payload)
        await self._drain(writer)

    async def _read_sync_failure(self, reader: asyncio.StreamReader) -> AdbSyncError:
        length = struct.unpack("<I", await self._read_exactly(reader, 4))[0]
        message = (await self._read_exactly(reader, length)).decode("utf-8", errors="replace")
        return AdbSyncError("ADB Sync operation failed", details={"message": message})

    async def _read_exactly(self, reader: asyncio.StreamReader, length: int) -> bytes:
        try:
            return await asyncio.wait_for(reader.readexactly(length), self.timeout)
        except asyncio.IncompleteReadError as exc:
            raise AdbSyncError(
                "ADB Sync connection closed unexpectedly",
                details={"expected": length, "received": len(exc.partial)},
            ) from exc
        except asyncio.TimeoutError as exc:
            raise AdbSyncError("ADB Sync operation timed out", details={"length": length, "timeout": self.timeout}) from exc

    async def _drain(self, writer: asyncio.StreamWriter) -> None:
        """Flush with a timeout.

        Without one, a device that stops reading wedges the write side forever
        and, because a transfer holds the manager semaphore for its whole
        duration, blocks every queued transfer behind it.
        """
        try:
            await asyncio.wait_for(writer.drain(), self.timeout)
        except asyncio.TimeoutError as exc:
            raise AdbSyncError(
                "ADB Sync write timed out; the device stopped accepting data",
                details={"timeout": self.timeout},
            ) from exc

    @staticmethod
    async def _notify(callback: ProgressCallback | None, transferred: int, total: int | None) -> None:
        if callback is None:
            return
        result = callback(transferred, total)
        if asyncio.iscoroutine(result):
            await result
