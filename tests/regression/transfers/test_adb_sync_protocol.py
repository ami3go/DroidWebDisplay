from __future__ import annotations

import asyncio
from pathlib import Path
import struct

import pytest

from droid_web_display.transfers.adb_sync import AdbSyncClient


async def read_host_request(reader: asyncio.StreamReader) -> str:
    length = int((await reader.readexactly(4)).decode("ascii"), 16)
    return (await reader.readexactly(length)).decode("utf-8")


async def accept_sync(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    assert await read_host_request(reader) == "host:transport:PHONE"
    writer.write(b"OKAY")
    await writer.drain()
    assert await read_host_request(reader) == "sync:"
    writer.write(b"OKAY")
    await writer.drain()


@pytest.mark.asyncio
async def test_structured_list_and_stat() -> None:
    calls = 0

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal calls
        calls += 1
        await accept_sync(reader, writer)
        command = await reader.readexactly(4)
        length = struct.unpack("<I", await reader.readexactly(4))[0]
        path = (await reader.readexactly(length)).decode()
        if command == b"LIST":
            assert path == "/sdcard/Download"
            name = b"result.zip"
            writer.write(b"DENT" + struct.pack("<IIII", 0o100664, 123, 456, len(name)) + name)
            writer.write(b"DONE" + bytes(16))
        else:
            assert command == b"STAT"
            writer.write(b"STAT" + struct.pack("<III", 0o100664, 123, 456))
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        client = AdbSyncClient(port=port)
        entries = await client.list("PHONE", "/sdcard/Download")
        assert entries[0].name == "result.zip"
        stat = await client.stat("PHONE", "/sdcard/Download/result.zip")
        assert stat.size == 123
        assert calls == 2
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_structured_push_and_pull(tmp_path: Path) -> None:
    payload = b"phase-five-data" * 1000
    operations = ["push", "stat", "pull"]
    received = bytearray()

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        operation = operations.pop(0)
        await accept_sync(reader, writer)
        command = await reader.readexactly(4)
        length = struct.unpack("<I", await reader.readexactly(4))[0]
        request = await reader.readexactly(length)
        if operation == "push":
            assert command == b"SEND"
            assert request.startswith(b"/sdcard/Download/data.bin,")
            while True:
                marker = await reader.readexactly(4)
                size = struct.unpack("<I", await reader.readexactly(4))[0]
                if marker == b"DATA":
                    received.extend(await reader.readexactly(size))
                else:
                    assert marker == b"DONE"
                    break
            writer.write(b"OKAY" + bytes(4))
        elif operation == "stat":
            assert command == b"STAT"
            writer.write(b"STAT" + struct.pack("<III", 0o100664, len(payload), 1))
        else:
            assert command == b"RECV"
            for offset in range(0, len(payload), 4096):
                chunk = payload[offset:offset + 4096]
                writer.write(b"DATA" + struct.pack("<I", len(chunk)) + chunk)
            writer.write(b"DONE" + bytes(4))
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        client = AdbSyncClient(port=port)
        source = tmp_path / "source.bin"
        source.write_bytes(payload)
        pushed = await client.push("PHONE", source, "/sdcard/Download/data.bin")
        assert pushed == len(payload)
        assert bytes(received) == payload
        target = tmp_path / "target.bin"
        pulled = await client.pull("PHONE", "/sdcard/Download/data.bin", target)
        assert pulled == len(payload)
        assert target.read_bytes() == payload
    finally:
        server.close()
        await server.wait_closed()
