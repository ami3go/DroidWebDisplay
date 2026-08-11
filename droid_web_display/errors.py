from __future__ import annotations


class BridgeError(RuntimeError):
    """Base error for the DroidWebDisplay service."""

    code = "bridge_error"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class AdbUnavailableError(BridgeError):
    code = "adb_unavailable"


class AdbCommandError(BridgeError):
    code = "adb_command_failed"


class DeviceNotFoundError(BridgeError):
    code = "device_not_found"


class DeviceNotReadyError(BridgeError):
    code = "device_not_ready"


class MultipleDevicesError(BridgeError):
    code = "multiple_devices"


class ArtifactError(BridgeError):
    code = "scrcpy_artifact_error"


class SessionError(BridgeError):
    code = "session_error"


class SessionNotFoundError(BridgeError):
    code = "session_not_found"


class SessionConflictError(BridgeError):
    code = "session_conflict"


class TunnelError(BridgeError):
    code = "tunnel_error"


class AdbSyncError(BridgeError):
    code = "adb_sync_error"


class TransferError(BridgeError):
    code = "transfer_error"


class TransferNotFoundError(TransferError):
    code = "transfer_not_found"


class TransferConflictError(TransferError):
    code = "transfer_conflict"


class TransferValidationError(TransferError):
    code = "transfer_validation"


class TransferCancelledError(TransferError):
    code = "transfer_cancelled"
