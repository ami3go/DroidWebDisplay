from __future__ import annotations

import contextlib
from dataclasses import replace
from pathlib import Path
from typing import Any

from droid_web_display.auth import AuthError, AuthService as _BaseAuthService
from droid_web_display.errors import TransferValidationError
from droid_web_display.models import ChannelName, SessionOptions, SessionState
from droid_web_display.scrcpy.encoder_tuning import encoder_tuning_store
from droid_web_display.scrcpy.session import SessionManager as _BaseSessionManager
from droid_web_display.transfers.manager import TransferManager as _BaseTransferManager
from droid_web_display.transfers.models import TransferDirection, TransferRecord


class HardenedAuthService(_BaseAuthService):
    """AuthService with a loopback-only bootstrap trust boundary.

    Existing PIN login may be used over an explicitly configured LAN HTTPS
    listener, but the first PIN must be established while the service is in
    local-only mode. This prevents a LAN client from claiming a newly reset
    authentication store.
    """

    def setup(self, pin: str, *, access_mode: str = "local", **kwargs: Any):  # type: ignore[override]
        if access_mode != "local":
            raise AuthError(
                "Initial PIN setup is only allowed from the local PC. Restart DroidWebDisplay in local-only mode first.",
                code="setup_requires_local",
            )
        return super().setup(pin, access_mode=access_mode, **kwargs)


class HardenedTransferManager(_BaseTransferManager):
    """Transfer manager with deterministic spool ownership and size symmetry."""

    async def start(self) -> None:
        await super().start()
        self._cleanup_orphaned_upload_spool()

    async def enqueue_upload(self, *, spool_path: Path, **kwargs: Any):  # type: ignore[override]
        spool = Path(spool_path)
        try:
            return await super().enqueue_upload(spool_path=spool, **kwargs)
        except BaseException:
            registered = False
            with contextlib.suppress(OSError):
                resolved_spool = spool.resolve()
                registered = any(
                    record.direction == TransferDirection.UPLOAD
                    and record.internal_local_path
                    and Path(record.internal_local_path).resolve() == resolved_spool
                    for record in self._records.values()
                )
            if not registered:
                with contextlib.suppress(OSError):
                    spool.unlink(missing_ok=True)
            raise

    async def _run_download(self, record: TransferRecord) -> None:
        remote = await self.sync.stat(record.serial, record.source_path)
        if remote.exists and not remote.is_directory and remote.size > self.maximum_file_size:
            raise TransferValidationError(
                "file exceeds configured maximum size",
                details={
                    "sourcePath": record.source_path,
                    "size": remote.size,
                    "maximumFileSize": self.maximum_file_size,
                },
            )
        await super()._run_download(record)

    def _cleanup_orphaned_upload_spool(self) -> None:
        referenced: set[Path] = set()
        for record in self._records.values():
            if record.direction != TransferDirection.UPLOAD or not record.internal_local_path:
                continue
            with contextlib.suppress(OSError):
                referenced.add(Path(record.internal_local_path).resolve())

        for path in self.upload_spool.glob("*.part"):
            try:
                if path.resolve() not in referenced:
                    path.unlink(missing_ok=True)
            except OSError:
                # A locked spool should not prevent the bridge from starting.
                continue


class ResilientSessionManager(_BaseSessionManager):
    """Keep optional channels isolated and safely apply explicit encoder tuning."""

    async def start_session(
        self,
        *,
        serial: str | None = None,
        options: SessionOptions | None = None,
    ):
        effective_serial = serial
        selected_options = options or SessionOptions()
        injected_preference: str | None = None

        if selected_options.video and selected_options.video_encoder is None:
            if effective_serial is None:
                selected = await self.select_device(None)
                effective_serial = selected.serial
            injected_preference = encoder_tuning_store().preference(effective_serial)
            if injected_preference:
                selected_options = replace(selected_options, video_encoder=injected_preference)

        try:
            return await super().start_session(serial=effective_serial, options=selected_options)
        except Exception as preferred_error:
            if not injected_preference or effective_serial is None:
                raise

            # A persisted manual encoder can become invalid after an Android/ROM
            # update even when the device serial remains unchanged. Do not let a
            # stale tuning value brick normal Auto operation: invalidate it and
            # retry exactly once using scrcpy's own encoder selection.
            encoder_tuning_store().invalidate_preference(
                effective_serial,
                expected=injected_preference,
                reason="preferred-encoder-start-failed",
            )
            fallback_options = replace(selected_options, video_encoder=None)
            try:
                session = await super().start_session(serial=effective_serial, options=fallback_options)
            except Exception as fallback_error:
                raise fallback_error from preferred_error
            session.server_log.append(
                f"preferred video encoder {injected_preference!r} failed; retried successfully with scrcpy auto"
            )
            return session

    async def stop_session(self, session_id: str, *, reason: str = "requested"):  # type: ignore[override]
        session = self._sessions.get(session_id)
        if (
            session is not None
            and reason.startswith("browser_audio_")
            and session.state in {SessionState.RUNNING, SessionState.RESIZING}
        ):
            channel = session.channels.pop(ChannelName.AUDIO, None)
            if channel is not None:
                with contextlib.suppress(Exception):
                    await channel.close()
            session.server_log.append(f"optional audio channel detached: {reason}")
            return session
        return await super().stop_session(session_id, reason=reason)


def install_runtime_hardening() -> None:
    """Install hardened implementations while preserving historical import paths."""

    import droid_web_display.auth as auth_module
    import droid_web_display.scrcpy as scrcpy_package
    import droid_web_display.scrcpy.session as session_module
    import droid_web_display.transfers as transfers_package
    import droid_web_display.transfers.manager as transfer_manager_module

    auth_module.AuthService = HardenedAuthService
    session_module.SessionManager = ResilientSessionManager
    scrcpy_package.SessionManager = ResilientSessionManager
    transfer_manager_module.TransferManager = HardenedTransferManager
    transfers_package.TransferManager = HardenedTransferManager
