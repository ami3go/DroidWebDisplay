from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BridgeConfig:
    repo_root: Path
    adb_executable: str = "adb"
    bind_host: str = "127.0.0.1"
    bind_port: int = 8765
    device_monitor_interval: float = 2.0
    transfer_concurrency: int = 1
    maximum_transfer_queue_length: int = 100
    maximum_file_size: int = 2 * 1024 * 1024 * 1024
    default_android_upload_directory: str = "/sdcard/Download/GptBridgeInbox"
    transfer_data_directory: Path | None = None
    default_download_directory: Path | None = None
    authentication_required: bool = True
    auth_data_file: Path | None = None
    network_mode: str = "local-only"
    allowed_client_networks: tuple[str, ...] = ()
    tls_enabled: bool = False
    tls_certificate_path: Path | None = None
    tls_private_key_path: Path | None = None
    configured_hostname: str | None = None
    network_config_file: Path | None = None

    def validate(self) -> None:
        if self.network_mode not in {"local-only", "lan-https"}:
            raise ValueError("network_mode must be local-only or lan-https")
        if self.network_mode == "local-only" and self.bind_host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Local-only mode requires a loopback bind address")
        if self.network_mode == "lan-https":
            from gpt_bridge.network_access import NetworkAccessConfig, TlsSettings
            NetworkAccessConfig(
                mode=self.network_mode,
                bind_address=self.bind_host,
                port=self.bind_port,
                allowed_networks=self.allowed_client_networks,
                hostname=self.configured_hostname,
                tls=TlsSettings(
                    enabled=self.tls_enabled,
                    certificate_path=str(self.tls_certificate_path) if self.tls_certificate_path else None,
                    private_key_path=str(self.tls_private_key_path) if self.tls_private_key_path else None,
                ),
            ).validate(require_files=True)
        if not 1 <= self.bind_port <= 65535:
            raise ValueError("bind_port must be in range 1..65535")
        if self.device_monitor_interval < 0.2:
            raise ValueError("device_monitor_interval must be at least 0.2 seconds")
        if not 1 <= self.transfer_concurrency <= 4:
            raise ValueError("transfer_concurrency must be in range 1..4")
        if self.maximum_transfer_queue_length < 1:
            raise ValueError("maximum_transfer_queue_length must be positive")
        if self.maximum_file_size < 1:
            raise ValueError("maximum_file_size must be positive")

    @property
    def resolved_transfer_data_directory(self) -> Path:
        return (self.transfer_data_directory or (self.repo_root / "data")).resolve()

    @property
    def resolved_default_download_directory(self) -> Path:
        return (self.default_download_directory or (self.repo_root / "downloads")).resolve()

    @property
    def resolved_auth_data_file(self) -> Path:
        return (self.auth_data_file or (self.resolved_transfer_data_directory / "auth.json")).resolve()

    @property
    def resolved_network_config_file(self) -> Path:
        return (self.network_config_file or (self.resolved_transfer_data_directory / "network-access.json")).resolve()

    def destination_profiles(self) -> dict[str, Path]:
        return {"default-downloads": self.resolved_default_download_directory}
