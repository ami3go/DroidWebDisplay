from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass
class OpaqueProxyMetrics:
    device_to_client_bytes: int = 0
    client_to_device_bytes: int = 0
    closed_reason: str | None = None


async def _copy(
    source: asyncio.StreamReader,
    destination: asyncio.StreamWriter,
    *,
    chunk_size: int,
    counter: str,
    metrics: OpaqueProxyMetrics,
) -> None:
    while True:
        data = await source.read(chunk_size)
        if not data:
            return
        destination.write(data)
        await destination.drain()
        setattr(metrics, counter, getattr(metrics, counter) + len(data))


async def relay_one_way(
    device_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    *,
    metrics: OpaqueProxyMetrics | None = None,
    chunk_size: int = 64 * 1024,
) -> OpaqueProxyMetrics:
    """Relay device bytes unchanged, respecting destination backpressure."""

    result = metrics or OpaqueProxyMetrics()
    try:
        await _copy(
            device_reader,
            client_writer,
            chunk_size=chunk_size,
            counter="device_to_client_bytes",
            metrics=result,
        )
        result.closed_reason = result.closed_reason or "device_eof"
    finally:
        client_writer.close()
        try:
            await client_writer.wait_closed()
        except (ConnectionError, RuntimeError):
            pass
    return result


async def relay_bidirectional(
    device_reader: asyncio.StreamReader,
    device_writer: asyncio.StreamWriter,
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    *,
    metrics: OpaqueProxyMetrics | None = None,
    chunk_size: int = 64 * 1024,
) -> OpaqueProxyMetrics:
    """Relay both directions without parsing or modifying payload bytes."""

    result = metrics or OpaqueProxyMetrics()
    to_client = asyncio.create_task(
        _copy(
            device_reader,
            client_writer,
            chunk_size=chunk_size,
            counter="device_to_client_bytes",
            metrics=result,
        )
    )
    to_device = asyncio.create_task(
        _copy(
            client_reader,
            device_writer,
            chunk_size=chunk_size,
            counter="client_to_device_bytes",
            metrics=result,
        )
    )
    tasks = {to_client, to_device}
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, return_exceptions=False)
        await asyncio.gather(*pending, return_exceptions=True)
        result.closed_reason = result.closed_reason or "channel_eof"
    finally:
        for writer in (client_writer, device_writer):
            writer.close()
        for writer in (client_writer, device_writer):
            try:
                await writer.wait_closed()
            except (ConnectionError, RuntimeError):
                pass
    return result
