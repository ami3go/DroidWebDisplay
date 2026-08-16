from __future__ import annotations

import asyncio
import contextlib
import secrets
import socket
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from droid_web_display.adb.client import AdbBackend, SpawnedAdbProcess
from droid_web_display.errors import (
    DeviceNotFoundError,
    DeviceNotReadyError,
    MultipleDevicesError,
    SessionConflictError,
    SessionError,
    SessionNotFoundError,
    TunnelError,
)
from droid_web_display.models import (
    AndroidDevice,
    ChannelName,
    DisplayMode,
    SessionOptions,
    SessionState,
)

from .artifact import ScrcpyArtifact
from .command import build_server_arguments, socket_name
from .virtual_display import (
    classify_application_log,
    classify_virtual_display_failure,
    parse_new_display_line,
)

Connector = Callable[[str, int], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]
ArtifactLoader = Callable[[], ScrcpyArtifact]

TERMINAL_SESSION_STATES = {
    SessionState.STOPPED,
    SessionState.DISCONNECTED,
    SessionState.FAILED,
}
MAX_RETAINED_TERMINATED_SESSIONS = 20



class PrefixedStreamReader:
    """StreamReader facade that returns validated transport bytes before raw data."""

    def __init__(self, reader: asyncio.StreamReader, prefix: bytes = b"") -> None:
        self._reader = reader
        self._prefix = bytearray(prefix)

    async def read(self, n: int = -1) -> bytes:
        if n == 0:
            return b""
        if n < 0:
            prefix = bytes(self._prefix)
            self._prefix.clear()
            return prefix + await self._reader.read()
        if self._prefix:
            take = min(n, len(self._prefix))
            chunk = bytes(self._prefix[:take])
            del self._prefix[:take]
            if take == n:
                return chunk
            return chunk + await self._reader.read(n - take)
        return await self._reader.read(n)

    async def readexactly(self, n: int) -> bytes:
        if n < 0:
            raise ValueError("n must be non-negative")
        if n == 0:
            return b""
        prefix = b""
        if self._prefix:
            take = min(n, len(self._prefix))
            prefix = bytes(self._prefix[:take])
            del self._prefix[:take]
            if take == n:
                return prefix
        try:
            return prefix + await self._reader.readexactly(n - len(prefix))
        except asyncio.IncompleteReadError as exc:
            raise asyncio.IncompleteReadError(prefix + exc.partial, n) from exc

    def at_eof(self) -> bool:
        return not self._prefix and self._reader.at_eof()


@dataclass
class ScrcpyChannel:
    name: ChannelName
    reader: PrefixedStreamReader
    writer: asyncio.StreamWriter
    opened_at: float = field(default_factory=time.time)
    bytes_from_device: int = 0
    bytes_to_device: int = 0
    attached_client: str | None = None
    attached_at: float | None = None
    relay_close_reason: str | None = None
    _attachment_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def claim(self, client_id: str) -> None:
        async with self._attachment_lock:
            if self.attached_client is not None:
                raise SessionConflictError(
                    f"scrcpy {self.name.value} channel already has a browser client",
                    details={"channel": self.name.value, "clientId": self.attached_client},
                )
            self.attached_client = client_id
            self.attached_at = time.time()
            self.relay_close_reason = None

    async def release(self, client_id: str, *, reason: str | None = None) -> None:
        async with self._attachment_lock:
            if self.attached_client == client_id:
                self.attached_client = None
                self.relay_close_reason = reason

    def to_dict(self) -> dict:
        return {
            "name": self.name.value,
            "openedAt": self.opened_at,
            "bytesFromDevice": self.bytes_from_device,
            "bytesToDevice": self.bytes_to_device,
            "attached": self.attached_client is not None,
            "attachedAt": self.attached_at,
            "relayCloseReason": self.relay_close_reason,
        }

    async def close(self) -> None:
        self.writer.close()
        with contextlib.suppress(
            asyncio.TimeoutError, ConnectionError, RuntimeError
        ):
            await asyncio.wait_for(self.writer.wait_closed(), timeout=1.0)


@dataclass
class ScrcpySession:
    session_id: str
    serial: str
    scid: int
    local_port: int
    socket_name: str
    options: SessionOptions
    state: SessionState = SessionState.STARTING
    channels: dict[ChannelName, ScrcpyChannel] = field(default_factory=dict)
    process: SpawnedAdbProcess | None = None
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    stopped_at: float | None = None
    stop_reason: str | None = None
    error: str | None = None
    server_log: deque[str] = field(default_factory=lambda: deque(maxlen=200))
    log_task: asyncio.Task[None] | None = None
    process_watch_task: asyncio.Task[None] | None = None
    first_channel_attempts: int = 0
    dummy_byte_validated: bool = False
    display_ready_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    display_id: int | None = None
    actual_width: int | None = None
    actual_height: int | None = None
    actual_dpi: int | None = None
    application_launch_result: str = "not-requested"
    application: str | None = None
    resize_count: int = 0
    last_requested_width: int | None = None
    last_requested_height: int | None = None
    cleanup_result: str = "not-started"
    server_arguments: tuple[str, ...] = field(default_factory=tuple)
    requested_ime_policy: str | None = None
    effective_ime_policy: str | None = None
    ime_policy_fallback_applied: bool = False
    virtual_display_warnings: list[str] = field(default_factory=list)
    virtual_display_failure_classification: str | None = None

    def to_dict(self) -> dict:
        virtual = self.options.virtual_display
        virtual_diagnostics = {
            "requested": self.options.display_mode == DisplayMode.VIRTUAL,
            "supported": True if self.options.display_mode == DisplayMode.VIRTUAL else None,
            "displayId": self.display_id,
            "requestedSize": f"{virtual.width}x{virtual.height}" if virtual else None,
            "actualSize": f"{self.actual_width}x{self.actual_height}" if self.actual_width and self.actual_height else None,
            "requestedDpi": virtual.dpi if virtual else None,
            "actualDpi": self.actual_dpi,
            "flexDisplay": virtual.flex_display if virtual else False,
            "systemDecorations": virtual.system_decorations if virtual else None,
            "destroyContentOnClose": virtual.destroy_content_on_close if virtual else None,
            "imePolicy": virtual.ime_policy.value if virtual else None,
            "requestedImePolicy": self.requested_ime_policy or (virtual.ime_policy.value if virtual else None),
            "effectiveImePolicy": self.effective_ime_policy or (virtual.ime_policy.value if virtual else None),
            "imePolicyFallbackApplied": self.ime_policy_fallback_applied,
            "warnings": list(self.virtual_display_warnings),
            "failureClassification": self.virtual_display_failure_classification,
            "startApp": virtual.start_app if virtual else None,
            "startAppPayload": virtual.start_app_payload if virtual else None,
            "applicationLaunchResult": self.application_launch_result,
            "application": self.application,
            "resizeCount": self.resize_count,
            "lastRequestedSize": f"{self.last_requested_width}x{self.last_requested_height}" if self.last_requested_width and self.last_requested_height else None,
            "cleanupResult": self.cleanup_result,
        }
        return {
            "sessionId": self.session_id,
            "serial": self.serial,
            "scid": f"{self.scid:08x}",
            "localPort": self.local_port,
            "socketName": self.socket_name,
            "state": self.state.value,
            "channels": [name.value for name in self.channels],
            "channelDiagnostics": {name.value: channel.to_dict() for name, channel in self.channels.items()},
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "stoppedAt": self.stopped_at,
            "stopReason": self.stop_reason,
            "error": self.error,
            "serverLogTail": list(self.server_log)[-80:],
            "serverArguments": list(self.server_arguments),
            "firstChannelAttempts": self.first_channel_attempts,
            "dummyByteValidated": self.dummy_byte_validated,
            "options": self.options.to_dict(),
            "displayMode": self.options.display_mode.value,
            "virtualDisplay": virtual_diagnostics,
        }


class SessionManager:
    REMOTE_SERVER_PATH = "/data/local/tmp/scrcpy-server.jar"

    def __init__(
        self,
        adb: AdbBackend,
        artifact: ScrcpyArtifact | None = None,
        *,
        artifact_loader: ArtifactLoader | None = None,
        connector: Connector = asyncio.open_connection,
        connect_timeout: float = 10.0,
        display_creation_timeout: float = 20.0,
        connect_retry_interval: float = 0.1,
        monitor_interval: float = 2.0,
    ) -> None:
        self.adb = adb
        self.artifact = artifact
        self.artifact_loader = artifact_loader
        self.connector = connector
        self.connect_timeout = connect_timeout
        self.display_creation_timeout = display_creation_timeout
        self.connect_retry_interval = connect_retry_interval
        self.monitor_interval = monitor_interval
        self._sessions: dict[str, ScrcpySession] = {}
        self._serial_index: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._monitor_task: asyncio.Task[None] | None = None
        self._closed = False

    async def start_monitor(self) -> None:
        if self._monitor_task and not self._monitor_task.done():
            return
        self._closed = False
        self._monitor_task = asyncio.create_task(self._monitor_devices(), name="droidwebdisplay-device-monitor")

    async def close(self) -> None:
        self._closed = True
        if self._monitor_task:
            self._monitor_task.cancel()
            await asyncio.gather(self._monitor_task, return_exceptions=True)
            self._monitor_task = None
        for session_id in list(self._sessions):
            await self.stop_session(session_id, reason="service_shutdown")

    async def list_devices(self, *, enrich: bool = True) -> list[AndroidDevice]:
        return await self.adb.list_devices(enrich=enrich)

    async def select_device(self, serial: str | None) -> AndroidDevice:
        devices = await self.list_devices(enrich=True)
        if serial:
            device = next((item for item in devices if item.serial == serial), None)
            if device is None:
                raise DeviceNotFoundError(
                    f"ADB device not found: {serial}",
                    details={"serial": serial, "devices": [item.to_dict() for item in devices]},
                )
            if not device.ready:
                raise DeviceNotReadyError(
                    f"ADB device {serial} is not ready: {device.state}",
                    details=device.to_dict(),
                )
            return device

        ready = [item for item in devices if item.ready]
        if not ready:
            raise DeviceNotReadyError(
                "No authorized ADB device is ready",
                details={"devices": [item.to_dict() for item in devices]},
            )
        if len(ready) > 1:
            raise MultipleDevicesError(
                "Multiple authorized ADB devices are connected; select an explicit serial",
                details={"devices": [item.to_dict() for item in ready]},
            )
        return ready[0]

    async def start_session(
        self,
        *,
        serial: str | None = None,
        options: SessionOptions | None = None,
    ) -> ScrcpySession:
        selected = await self.select_device(serial)
        artifact = self._resolve_artifact()
        selected_options = options or SessionOptions()
        selected_options.validate()
        if selected_options.display_mode == DisplayMode.VIRTUAL and (selected.sdk or 0) < 29:
            raise SessionError(
                "Virtual Display mode requires Android 10 / API 29 or newer",
                details={"serial": selected.serial, "deviceApi": selected.sdk, "minimumApi": 29},
            )

        async with self._lock:
            existing_id = self._serial_index.get(selected.serial)
            if existing_id:
                existing = self._sessions.get(existing_id)
                if existing and existing.state in {
                    SessionState.PROBING,
                    SessionState.STARTING,
                    SessionState.CREATING_DISPLAY,
                    SessionState.LAUNCHING_APP,
                    SessionState.CONNECTING_VIDEO,
                    SessionState.CONNECTING_CONTROL,
                    SessionState.RUNNING,
                    SessionState.RESIZING,
                }:
                    raise SessionConflictError(
                        f"A session is already active for device {selected.serial}",
                        details={"sessionId": existing.session_id, "serial": selected.serial},
                    )
            session_id = secrets.token_urlsafe(18)
            scid = secrets.randbelow(0x80000000)
            port = self._reserve_local_port()
            session = ScrcpySession(
                session_id=session_id,
                serial=selected.serial,
                scid=scid,
                local_port=port,
                socket_name=socket_name(scid),
                options=selected_options,
            )
            if selected_options.display_mode == DisplayMode.VIRTUAL and selected_options.virtual_display:
                session.application = selected_options.virtual_display.start_app or None
                session.application_launch_result = "pending-control-message" if session.application else "not-requested"
                session.state = SessionState.CREATING_DISPLAY
            self._sessions[session_id] = session
            self._serial_index[selected.serial] = session_id

        try:
            await self._start_session_resources(session, artifact)
        except Exception as exc:
            session.state = SessionState.FAILED
            session.error = str(exc)
            session.stop_reason = "start_failed"
            await self._cleanup_session_resources(session)
            async with self._lock:
                self._serial_index.pop(session.serial, None)
            if isinstance(exc, SessionError):
                raise
            raise SessionError(
                f"Unable to start scrcpy session: {exc}",
                details={
                    "sessionId": session.session_id,
                    "serial": session.serial,
                    "serverArguments": list(session.server_arguments),
                    "serverLog": list(session.server_log),
                    "classification": session.virtual_display_failure_classification,
                },
            ) from exc

        session.state = SessionState.RUNNING
        session.started_at = time.time()
        await self.start_monitor()
        return session

    async def _start_session_resources(
        self, session: ScrcpySession, artifact: ScrcpyArtifact
    ) -> None:
        await self.adb.push(session.serial, artifact.path, self.REMOTE_SERVER_PATH)
        await self.adb.create_forward(session.serial, session.local_port, session.socket_name)

        args = build_server_arguments(artifact.version, session.scid, session.options)
        session.server_arguments = tuple(args)
        session.process = await self.adb.spawn_server(session.serial, args)
        session.log_task = asyncio.create_task(self._collect_process_log(session))
        session.process_watch_task = asyncio.create_task(
            self._watch_server_process(session),
            name=f"droidwebdisplay-server-watch-{session.session_id}",
        )

        deadline = asyncio.get_running_loop().time() + self.connect_timeout
        ordered_channels = session.options.ordered_channels()
        for index, channel_name in enumerate(ordered_channels):
            if index == 0:
                reader, writer = await self._connect_first_channel_with_dummy(
                    session,
                    channel_name,
                    deadline=deadline,
                )
            else:
                raw_reader, writer = await self._connect_with_retry(
                    session,
                    channel_name,
                    deadline=deadline,
                )
                reader = PrefixedStreamReader(raw_reader)
            session.channels[channel_name] = ScrcpyChannel(channel_name, reader, writer)

        if session.options.display_mode == DisplayMode.VIRTUAL:
            await self._wait_for_virtual_display(session)

    async def _wait_for_virtual_display(self, session: ScrcpySession) -> None:
        """Wait independently of channel connection time and preserve failure evidence."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.display_creation_timeout
        while loop.time() < deadline:
            if session.display_ready_event.is_set():
                return
            process = session.process
            if process and process.returncode is not None:
                await self._drain_process_log(session, timeout=1.0)
                break
            try:
                await asyncio.wait_for(session.display_ready_event.wait(), timeout=min(0.25, deadline - loop.time()))
                return
            except asyncio.TimeoutError:
                continue

        await self._drain_process_log(session, timeout=1.0)
        logs = list(session.server_log)
        classification = classify_virtual_display_failure(logs)
        session.virtual_display_failure_classification = classification
        display_state_tail = ""
        display_state = getattr(self.adb, "display_state", None)
        if callable(display_state):
            with contextlib.suppress(Exception):
                display_state_tail = (await display_state(session.serial))[-8000:]
        raise SessionError(
            "Android did not create the requested virtual display",
            details={
                "serial": session.serial,
                "timeoutSeconds": self.display_creation_timeout,
                "classification": classification,
                "serverArguments": list(session.server_arguments),
                "serverLog": logs,
                "displayStateTail": display_state_tail,
                "processReturnCode": session.process.returncode if session.process else None,
            },
        )

    async def _drain_process_log(self, session: ScrcpySession, *, timeout: float = 1.0) -> None:
        task = session.log_task
        if not task or task.done():
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return

    async def _connect_first_channel_with_dummy(
        self,
        session: ScrcpySession,
        channel_name: ChannelName,
        *,
        deadline: float,
    ) -> tuple[PrefixedStreamReader, asyncio.StreamWriter]:
        """Connect the first forwarded channel and validate scrcpy's dummy byte.

        An ADB forward may accept a host TCP connection even while no Android
        localabstract socket is listening. scrcpy sends a zero dummy byte on the
        first accepted channel specifically so clients can detect that condition.
        """
        loop = asyncio.get_running_loop()
        last_error: Exception | None = None
        while loop.time() < deadline:
            process = session.process
            if process and process.returncode is not None:
                raise TunnelError(
                    f"scrcpy server exited before {channel_name.value} dummy byte",
                    details={"returncode": process.returncode, "serverLog": list(session.server_log)},
                )
            session.first_channel_attempts += 1
            raw_reader: asyncio.StreamReader | None = None
            writer: asyncio.StreamWriter | None = None
            try:
                raw_reader, writer = await self.connector("127.0.0.1", session.local_port)
                remaining = max(0.0, deadline - loop.time())
                if remaining <= 0:
                    raise asyncio.TimeoutError
                dummy = await asyncio.wait_for(raw_reader.readexactly(1), timeout=min(0.75, remaining))
                if dummy != b"\x00":
                    raise TunnelError(
                        "Invalid scrcpy dummy byte on first channel",
                        details={"value": dummy.hex(), "channel": channel_name.value},
                    )
                session.dummy_byte_validated = True
                return PrefixedStreamReader(raw_reader, dummy), writer
            except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, OSError, TunnelError) as exc:
                last_error = exc
                if writer is not None:
                    writer.close()
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(writer.wait_closed(), timeout=0.5)
                await asyncio.sleep(self.connect_retry_interval)
        raise TunnelError(
            f"Timed out waiting for scrcpy {channel_name.value} dummy byte",
            details={
                "serial": session.serial,
                "port": session.local_port,
                "socketName": session.socket_name,
                "attempts": session.first_channel_attempts,
                "lastError": repr(last_error),
                "serverLog": list(session.server_log),
            },
        )

    async def _connect_with_retry(
        self,
        session: ScrcpySession,
        channel_name: ChannelName,
        *,
        deadline: float,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        last_error: Exception | None = None
        loop = asyncio.get_running_loop()
        while loop.time() < deadline:
            process = session.process
            if process and process.returncode is not None:
                raise TunnelError(
                    f"scrcpy server exited before {channel_name.value} connected",
                    details={"returncode": process.returncode, "serverLog": list(session.server_log)},
                )
            try:
                return await self.connector("127.0.0.1", session.local_port)
            except (ConnectionError, OSError) as exc:
                last_error = exc
                await asyncio.sleep(self.connect_retry_interval)
        raise TunnelError(
            f"Timed out connecting scrcpy {channel_name.value} channel",
            details={
                "serial": session.serial,
                "port": session.local_port,
                "socketName": session.socket_name,
                "lastError": repr(last_error),
                "serverLog": list(session.server_log),
            },
        )

    async def stop_session(self, session_id: str, *, reason: str = "requested") -> ScrcpySession:
        session = self._sessions.get(session_id)
        if not session:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        if session.state in {
            SessionState.STOPPING,
            SessionState.STOPPED,
            SessionState.DISCONNECTED,
            SessionState.FAILED,
        }:
            return session
        session.state = SessionState.STOPPING
        session.stop_reason = reason
        await self._cleanup_session_resources(session)
        session.state = (
            SessionState.DISCONNECTED
            if reason in {"device_disconnected", "server_terminated"}
            else SessionState.STOPPED
        )
        session.stopped_at = time.time()
        async with self._lock:
            self._serial_index.pop(session.serial, None)
            self._prune_terminated()
        return session

    def _prune_terminated(self) -> None:
        """Cap how many finished sessions stay in memory.

        Terminated sessions are kept so clients can still read their final
        state, but every one of them is re-serialised into the health,
        diagnostics and /ws/v1/events payloads, so the backlog has to be
        bounded rather than growing for the lifetime of the process.
        """
        terminated = [
            item
            for item in self._sessions.values()
            if item.state in TERMINAL_SESSION_STATES
        ]
        excess = len(terminated) - MAX_RETAINED_TERMINATED_SESSIONS
        if excess <= 0:
            return
        terminated.sort(key=lambda item: item.stopped_at or item.created_at)
        for item in terminated[:excess]:
            self._sessions.pop(item.session_id, None)

    async def _cleanup_session_resources(self, session: ScrcpySession) -> None:
        if session.options.display_mode == DisplayMode.VIRTUAL:
            session.cleanup_result = "in-progress"
        for channel in list(session.channels.values()):
            await channel.close()
        session.channels.clear()

        with contextlib.suppress(Exception):
            await self.adb.remove_forward(session.serial, session.local_port)

        process = session.process
        if process and process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                with contextlib.suppress(Exception):
                    await process.wait()
        await self._drain_process_log(session, timeout=1.0)
        session.process = None

        current_task = asyncio.current_task()
        if session.process_watch_task and session.process_watch_task is not current_task:
            session.process_watch_task.cancel()
            await asyncio.gather(session.process_watch_task, return_exceptions=True)
            session.process_watch_task = None

        if session.log_task:
            session.log_task.cancel()
            await asyncio.gather(session.log_task, return_exceptions=True)
            session.log_task = None
        if session.options.display_mode == DisplayMode.VIRTUAL:
            session.cleanup_result = "server-released-display"

    async def _watch_server_process(self, session: ScrcpySession) -> None:
        process = session.process
        if not process:
            return
        returncode = await process.wait()
        await self._drain_process_log(session, timeout=1.0)
        if session.state not in {
            SessionState.PROBING,
            SessionState.STARTING,
            SessionState.CREATING_DISPLAY,
            SessionState.LAUNCHING_APP,
            SessionState.CONNECTING_VIDEO,
            SessionState.CONNECTING_CONTROL,
            SessionState.RUNNING,
            SessionState.RESIZING,
        }:
            return
        session.error = f"scrcpy server terminated with return code {returncode}"
        try:
            await self.stop_session(session.session_id, reason="server_terminated")
        except Exception as exc:
            session.state = SessionState.FAILED
            session.error = f"{session.error}; cleanup failed: {exc}"

    async def _collect_process_log(self, session: ScrcpySession) -> None:
        process = session.process
        if not process:
            return

        async def consume(stream: asyncio.StreamReader | None, prefix: str) -> None:
            if not stream:
                return
            while True:
                line = await stream.readline()
                if not line:
                    return
                text = prefix + line.decode("utf-8", errors="replace").rstrip()
                session.server_log.append(text)
                self._handle_server_log_line(session, text)

        await asyncio.gather(consume(process.stdout, "stdout: "), consume(process.stderr, "stderr: "))

    @staticmethod
    def _handle_server_log_line(session: ScrcpySession, line: str) -> None:
        lifecycle = parse_new_display_line(line)
        if lifecycle:
            session.display_id = lifecycle.display_id
            session.actual_width = lifecycle.width
            session.actual_height = lifecycle.height
            session.actual_dpi = lifecycle.dpi
            session.display_ready_event.set()
        app_result = classify_application_log(line)
        if app_result:
            session.application_launch_result, package = app_result
            if package:
                session.application = package

    async def _monitor_devices(self) -> None:
        while not self._closed:
            try:
                devices = await self.adb.list_devices(enrich=False)
                ready_serials = {device.serial for device in devices if device.ready}
                active = [
                    session
                    for session in self._sessions.values()
                    if session.state in {
                        SessionState.PROBING,
                        SessionState.STARTING,
                        SessionState.CREATING_DISPLAY,
                        SessionState.LAUNCHING_APP,
                        SessionState.CONNECTING_VIDEO,
                        SessionState.CONNECTING_CONTROL,
                        SessionState.RUNNING,
                        SessionState.RESIZING,
                    }
                ]
                for session in active:
                    if session.serial not in ready_serials:
                        await self.stop_session(session.session_id, reason="device_disconnected")
            except asyncio.CancelledError:
                raise
            except Exception:
                # The monitor is advisory. A transient adb failure must not crash
                # the service or silently reassign sessions to another device.
                pass
            await asyncio.sleep(self.monitor_interval)

    def record_virtual_resize(self, session_id: str, width: int, height: int) -> ScrcpySession:
        session = self.get_session(session_id)
        virtual = session.options.virtual_display
        if session.options.display_mode != DisplayMode.VIRTUAL or virtual is None or not virtual.flex_display:
            raise SessionError("Resize is valid only for a running flex virtual-display session")
        if session.state != SessionState.RUNNING:
            raise SessionError(f"Cannot resize session in state {session.state.value}")
        if not 640 <= width <= 3840 or not 480 <= height <= 2160:
            raise SessionError("Requested flex-display dimensions are outside the safe range")
        session.resize_count += 1
        session.last_requested_width = width
        session.last_requested_height = height
        return session

    def mark_application_launch(self, session_id: str, result: str) -> ScrcpySession:
        session = self.get_session(session_id)
        if result not in {"sent", "success", "failed"}:
            raise ValueError("Unsupported application launch result")
        session.application_launch_result = result
        return session

    def get_session(self, session_id: str) -> ScrcpySession:
        session = self._sessions.get(session_id)
        if not session:
            raise SessionNotFoundError(f"Session not found: {session_id}")
        return session

    def list_sessions(self) -> list[ScrcpySession]:
        return sorted(self._sessions.values(), key=lambda item: item.created_at)

    def _resolve_artifact(self) -> ScrcpyArtifact:
        if self.artifact is not None:
            return self.artifact
        if self.artifact_loader is None:
            raise SessionError("No scrcpy server artifact or artifact loader is configured")
        artifact = self.artifact_loader()
        self.artifact = artifact
        return artifact

    @staticmethod
    def _reserve_local_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
            handle.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            handle.bind(("127.0.0.1", 0))
            return int(handle.getsockname()[1])
