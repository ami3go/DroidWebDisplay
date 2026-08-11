from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from gpt_bridge.models import AndroidDevice, DisplayMode, SessionOptions, VirtualDisplayOptions
from gpt_bridge.scrcpy.artifact import ScrcpyArtifact
from gpt_bridge.scrcpy.session import SessionManager
from tests.regression.session.fakes import FakeAdb, FakeProcess


class VirtualFakeAdb(FakeAdb):
    async def spawn_server(self, serial: str, server_args):  # type: ignore[no-untyped-def]
        process = FakeProcess()
        self.server_args.append((serial, tuple(server_args)))
        self.processes.append(process)
        process.stderr.feed_data(b"[server] INFO: New display: 1600x900/240 (id=7)\n")
        return process


@pytest.mark.asyncio
async def test_virtual_session_parses_display_and_cleans_up(tmp_path: Path) -> None:
    adb = VirtualFakeAdb([AndroidDevice("PHONE", "device", sdk=33)])
    artifact_path = tmp_path / "scrcpy-server-v4.1"
    artifact_path.write_bytes(b"server")
    artifact = ScrcpyArtifact(artifact_path, "4.1", "a" * 40, "b" * 64, "scrcpy-4.1")
    manager = SessionManager(adb, artifact, connect_timeout=2.0)
    session = await manager.start_session(
        serial="PHONE",
        options=SessionOptions(
            display_mode=DisplayMode.VIRTUAL,
            virtual_display=VirtualDisplayOptions(),
            max_size=0,
            video_bit_rate=12_000_000,
            max_fps=60,
        ),
    )
    assert session.display_id == 7
    assert session.actual_width == 1600
    assert session.actual_height == 900
    assert session.actual_dpi == 240
    assert session.to_dict()["virtualDisplay"]["requested"] is True
    stopped = await manager.stop_session(session.session_id)
    assert stopped.cleanup_result == "server-released-display"
    await manager.close()


class DelayedVirtualFakeAdb(FakeAdb):
    async def spawn_server(self, serial: str, server_args):  # type: ignore[no-untyped-def]
        process = FakeProcess()
        self.server_args.append((serial, tuple(server_args)))
        self.processes.append(process)

        async def emit_lifecycle() -> None:
            await asyncio.sleep(0.25)
            process.stderr.feed_data(b"[server] INFO: New display: 1600x900/240 (id=9)\n")

        asyncio.create_task(emit_lifecycle())
        return process


@pytest.mark.asyncio
async def test_virtual_display_has_independent_creation_timeout(tmp_path: Path) -> None:
    adb = DelayedVirtualFakeAdb([AndroidDevice("PHONE", "device", sdk=33)])
    artifact_path = tmp_path / "scrcpy-server-v4.1"
    artifact_path.write_bytes(b"server")
    artifact = ScrcpyArtifact(artifact_path, "4.1", "a" * 40, "b" * 64, "scrcpy-4.1")
    manager = SessionManager(
        adb, artifact, connect_timeout=0.15, display_creation_timeout=0.75, connect_retry_interval=0.01
    )
    session = await manager.start_session(
        serial="PHONE",
        options=SessionOptions(
            display_mode=DisplayMode.VIRTUAL,
            virtual_display=VirtualDisplayOptions(),
            max_size=0,
        ),
    )
    assert session.display_id == 9
    assert session.server_arguments
    await manager.stop_session(session.session_id)
    await manager.close()
