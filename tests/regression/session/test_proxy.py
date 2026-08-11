import asyncio

import pytest

from gpt_bridge.proxy.opaque import relay_bidirectional


@pytest.mark.asyncio
async def test_bidirectional_proxy_preserves_binary_bytes() -> None:
    device_received = bytearray()
    client_received = bytearray()
    device_connected = asyncio.Event()
    client_connected = asyncio.Event()
    device_streams = None
    client_streams = None

    async def device_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal device_streams
        device_streams = (reader, writer)
        device_connected.set()

    async def client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal client_streams
        client_streams = (reader, writer)
        client_connected.set()

    device_server = await asyncio.start_server(device_handler, "127.0.0.1", 0)
    client_server = await asyncio.start_server(client_handler, "127.0.0.1", 0)
    device_port = device_server.sockets[0].getsockname()[1]
    client_port = client_server.sockets[0].getsockname()[1]

    bridge_device_reader, bridge_device_writer = await asyncio.open_connection("127.0.0.1", device_port)
    bridge_client_reader, bridge_client_writer = await asyncio.open_connection("127.0.0.1", client_port)
    await device_connected.wait()
    await client_connected.wait()
    assert device_streams and client_streams
    device_reader, device_writer = device_streams
    client_reader, client_writer = client_streams

    task = asyncio.create_task(
        relay_bidirectional(
            bridge_device_reader,
            bridge_device_writer,
            bridge_client_reader,
            bridge_client_writer,
        )
    )
    device_payload = bytes(range(256)) + b"\x00\xffdevice"
    client_payload = b"control\x00\xff" + bytes(reversed(range(256)))
    device_writer.write(device_payload)
    await device_writer.drain()
    client_writer.write(client_payload)
    await client_writer.drain()

    client_received.extend(await asyncio.wait_for(client_reader.readexactly(len(device_payload)), timeout=1))
    device_received.extend(await asyncio.wait_for(device_reader.readexactly(len(client_payload)), timeout=1))
    assert bytes(client_received) == device_payload
    assert bytes(device_received) == client_payload

    device_writer.close()
    client_writer.close()
    await asyncio.gather(device_writer.wait_closed(), client_writer.wait_closed())
    metrics = await asyncio.wait_for(task, timeout=1)
    assert metrics.device_to_client_bytes == len(device_payload)
    assert metrics.client_to_device_bytes == len(client_payload)

    device_server.close()
    client_server.close()
    await device_server.wait_closed()
    await client_server.wait_closed()
