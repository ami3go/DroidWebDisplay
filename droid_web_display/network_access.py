from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import ipaddress
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
from typing import Any, Iterable

import psutil
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

NETWORK_SCHEMA_VERSION = 1
LOCAL_ONLY = "local-only"
LAN_HTTPS = "lan-https"
DEFAULT_PORT = 8765
DEFAULT_RULE_NAME = "DroidWebDisplay LAN Access"


class NetworkAccessError(RuntimeError):
    def __init__(self, message: str, *, code: str = "network_access_error") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class TlsSettings:
    enabled: bool = False
    certificate_path: str | None = None
    private_key_path: str | None = None
    certificate_source: str = "generated"

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "certificatePath": self.certificate_path,
            "privateKeyPath": self.private_key_path,
            "certificateSource": self.certificate_source,
        }


@dataclass(frozen=True)
class FirewallSettings:
    manage_rule: bool = False
    rule_name: str = DEFAULT_RULE_NAME

    def to_dict(self) -> dict[str, Any]:
        return {"manageRule": self.manage_rule, "ruleName": self.rule_name}


@dataclass(frozen=True)
class NetworkAccessConfig:
    schema_version: int = NETWORK_SCHEMA_VERSION
    mode: str = LOCAL_ONLY
    bind_address: str = "127.0.0.1"
    port: int = DEFAULT_PORT
    allowed_networks: tuple[str, ...] = ()
    hostname: str | None = None
    tls: TlsSettings = field(default_factory=TlsSettings)
    firewall: FirewallSettings = field(default_factory=FirewallSettings)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NetworkAccessConfig":
        tls = value.get("tls") or {}
        firewall = value.get("firewall") or {}
        config = cls(
            schema_version=int(value.get("schemaVersion", NETWORK_SCHEMA_VERSION)),
            mode=str(value.get("mode", LOCAL_ONLY)),
            bind_address=str(value.get("bindAddress", "127.0.0.1")),
            port=int(value.get("port", DEFAULT_PORT)),
            allowed_networks=tuple(str(item) for item in value.get("allowedNetworks", [])),
            hostname=(str(value.get("hostname")).strip() if value.get("hostname") else None),
            tls=TlsSettings(
                enabled=bool(tls.get("enabled", False)),
                certificate_path=(str(tls.get("certificatePath")) if tls.get("certificatePath") else None),
                private_key_path=(str(tls.get("privateKeyPath")) if tls.get("privateKeyPath") else None),
                certificate_source=str(tls.get("certificateSource", "generated")),
            ),
            firewall=FirewallSettings(
                manage_rule=bool(firewall.get("manageRule", False)),
                rule_name=str(firewall.get("ruleName", DEFAULT_RULE_NAME)),
            ),
        )
        return config.validate()

    def validate(self, *, require_files: bool = False) -> "NetworkAccessConfig":
        if self.schema_version != NETWORK_SCHEMA_VERSION:
            raise NetworkAccessError("Unsupported network configuration schema", code="network_schema")
        if self.mode not in {LOCAL_ONLY, LAN_HTTPS}:
            raise NetworkAccessError("Unsupported network access mode", code="network_mode")
        if not 1 <= self.port <= 65535:
            raise NetworkAccessError("Port must be between 1 and 65535", code="network_port")
        try:
            address = ipaddress.ip_address(self.bind_address)
        except ValueError as exc:
            raise NetworkAccessError("Bind address must be a valid IP address", code="network_address") from exc
        if self.mode == LOCAL_ONLY:
            if not address.is_loopback:
                raise NetworkAccessError("Local-only mode must use a loopback address", code="network_address")
            if self.tls.enabled:
                raise NetworkAccessError("Local-only mode does not use TLS", code="network_tls")
            return self
        if address.version != 4 or address.is_loopback or not address.is_private or address.is_link_local:
            raise NetworkAccessError("LAN mode requires a specific private IPv4 address", code="network_address")
        if self.bind_address == "0.0.0.0":
            raise NetworkAccessError("Binding to every interface is not allowed", code="network_address")
        if not self.tls.enabled:
            raise NetworkAccessError("LAN mode requires HTTPS", code="network_tls")
        if not self.allowed_networks:
            raise NetworkAccessError("LAN mode requires at least one allowed network", code="network_allowlist")
        for entry in self.allowed_networks:
            try:
                network = ipaddress.ip_network(entry, strict=False)
            except ValueError as exc:
                raise NetworkAccessError(f"Invalid allowed network: {entry}", code="network_allowlist") from exc
            if network.version != 4 or not network.is_private or network.prefixlen < 16:
                raise NetworkAccessError(
                    f"Allowed network must be private IPv4 and /16 or narrower: {entry}",
                    code="network_allowlist",
                )
        if require_files:
            if not self.tls.certificate_path or not Path(self.tls.certificate_path).is_file():
                raise NetworkAccessError("TLS certificate file is missing", code="network_tls")
            if not self.tls.private_key_path or not Path(self.tls.private_key_path).is_file():
                raise NetworkAccessError("TLS private-key file is missing", code="network_tls")
        if not self.firewall.rule_name.strip():
            raise NetworkAccessError("Firewall rule name cannot be empty", code="network_firewall")
        return self

    def to_dict(self, *, redact_private_key: bool = False) -> dict[str, Any]:
        tls = self.tls.to_dict()
        if redact_private_key and tls["privateKeyPath"]:
            tls["privateKeyPath"] = "configured"
        return {
            "schemaVersion": self.schema_version,
            "mode": self.mode,
            "bindAddress": self.bind_address,
            "port": self.port,
            "allowedNetworks": list(self.allowed_networks),
            "hostname": self.hostname,
            "tls": tls,
            "firewall": self.firewall.to_dict(),
        }

    @property
    def scheme(self) -> str:
        return "https" if self.mode == LAN_HTTPS else "http"

    @property
    def primary_url(self) -> str:
        host = self.hostname or self.bind_address
        return f"{self.scheme}://{host}:{self.port}"


@dataclass(frozen=True)
class NetworkInterfaceInfo:
    name: str
    address: str
    prefix_length: int
    network: str
    private: bool
    loopback: bool
    adapter_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "prefixLength": self.prefix_length,
            "network": self.network,
            "private": self.private,
            "loopback": self.loopback,
            "adapterType": self.adapter_type,
        }


class NetworkConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path.resolve()

    def load(self) -> NetworkAccessConfig:
        if not self.path.is_file():
            return NetworkAccessConfig()
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NetworkAccessError(f"Network configuration is unreadable: {self.path}", code="network_store") from exc
        if not isinstance(value, dict):
            raise NetworkAccessError("Network configuration must be a JSON object", code="network_store")
        return NetworkAccessConfig.from_dict(value)

    def save(self, config: NetworkAccessConfig) -> None:
        config.validate(require_files=config.mode == LAN_HTTPS)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, self.path)

    def reset_local_only(self, *, port: int = DEFAULT_PORT) -> NetworkAccessConfig:
        config = NetworkAccessConfig(port=port)
        self.save(config)
        return config


def _adapter_type(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("wi-fi", "wifi", "wireless", "wlan")):
        return "wifi"
    if any(token in lowered for token in ("ethernet", "eth")):
        return "ethernet"
    if any(token in lowered for token in ("vpn", "tun", "tap", "wireguard")):
        return "vpn"
    if any(token in lowered for token in ("virtual", "vmware", "hyper-v", "vbox", "docker", "wsl")):
        return "virtual"
    return "other"


def list_network_interfaces() -> list[NetworkInterfaceInfo]:
    stats = psutil.net_if_stats()
    result: list[NetworkInterfaceInfo] = []
    for name, entries in psutil.net_if_addrs().items():
        if name in stats and not stats[name].isup:
            continue
        for entry in entries:
            if entry.family != socket.AF_INET:
                continue
            try:
                address = ipaddress.ip_address(entry.address)
                network = ipaddress.ip_network(f"{entry.address}/{entry.netmask}", strict=False)
            except ValueError:
                continue
            if address.is_loopback or address.is_link_local or address.is_unspecified:
                continue
            if not address.is_private:
                continue
            result.append(NetworkInterfaceInfo(
                name=name,
                address=str(address),
                prefix_length=network.prefixlen,
                network=str(network),
                private=True,
                loopback=False,
                adapter_type=_adapter_type(name),
            ))
    return sorted(result, key=lambda item: (item.adapter_type not in {"ethernet", "wifi"}, item.name.lower(), item.address))


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def generate_certificate(
    certificate_path: Path,
    private_key_path: Path,
    *,
    bind_address: str,
    hostname: str | None = None,
    validity_days: int = 365,
) -> dict[str, Any]:
    if not 30 <= validity_days <= 825:
        raise NetworkAccessError("Certificate validity must be between 30 and 825 days", code="network_certificate")
    address = ipaddress.ip_address(bind_address)
    if address.version != 4 or not address.is_private or address.is_loopback:
        raise NetworkAccessError("Certificate LAN address must be private IPv4", code="network_certificate")
    common_name = hostname or socket.gethostname() or "DroidWebDisplay"
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.now(timezone.utc)
    san_values: list[x509.GeneralName] = [
        x509.IPAddress(address),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        x509.DNSName("localhost"),
        x509.DNSName(common_name),
    ]
    host = socket.gethostname()
    if host and host != common_name:
        san_values.append(x509.DNSName(host))
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "DroidWebDisplay"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=validity_days))
        .add_extension(x509.SubjectAlternativeName(san_values), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    _write_private(
        private_key_path,
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )
    certificate_path.parent.mkdir(parents=True, exist_ok=True)
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return validate_certificate_pair(certificate_path, private_key_path, bind_address=bind_address, hostname=hostname)


def validate_certificate_pair(
    certificate_path: Path,
    private_key_path: Path,
    *,
    bind_address: str,
    hostname: str | None = None,
) -> dict[str, Any]:
    try:
        certificate = x509.load_pem_x509_certificate(certificate_path.read_bytes())
        key = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as exc:
        raise NetworkAccessError("Certificate or private key cannot be parsed", code="network_certificate") from exc
    cert_public = certificate.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    key_public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if cert_public != key_public:
        raise NetworkAccessError("Private key does not match certificate", code="network_certificate")
    now = datetime.now(timezone.utc)
    if certificate.not_valid_after_utc <= now:
        raise NetworkAccessError("Certificate has expired", code="network_certificate")
    try:
        san = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except x509.ExtensionNotFound as exc:
        raise NetworkAccessError("Certificate does not contain Subject Alternative Names", code="network_certificate") from exc
    ip_values = {str(item) for item in san.get_values_for_type(x509.IPAddress)}
    dns_values = {str(item).lower() for item in san.get_values_for_type(x509.DNSName)}
    if bind_address not in ip_values:
        raise NetworkAccessError("Certificate SAN does not include selected LAN address", code="network_certificate")
    if hostname and hostname.lower() not in dns_values:
        raise NetworkAccessError("Certificate SAN does not include configured hostname", code="network_certificate")
    return {
        "subject": certificate.subject.rfc4514_string(),
        "notBefore": certificate.not_valid_before_utc.isoformat(),
        "notAfter": certificate.not_valid_after_utc.isoformat(),
        "ipAddresses": sorted(ip_values),
        "dnsNames": sorted(dns_values),
        "sha256": certificate.fingerprint(hashes.SHA256()).hex(),
    }


class NetworkPolicy:
    def __init__(self, config: NetworkAccessConfig) -> None:
        self.config = config.validate(require_files=False)
        self.allowed_networks = tuple(ipaddress.ip_network(item, strict=False) for item in config.allowed_networks)

    def client_allowed(self, client_host: str | None) -> bool:
        if client_host == "testclient":
            return True
        if not client_host or client_host == "localhost":
            return self.config.mode == LOCAL_ONLY
        try:
            address = ipaddress.ip_address(client_host)
        except ValueError:
            return False
        if address.is_loopback:
            return True
        if self.config.mode != LAN_HTTPS:
            return False
        return any(address in network for network in self.allowed_networks)

    @property
    def allowed_hostnames(self) -> set[str]:
        values = {"127.0.0.1", "localhost", "[::1]", self.config.bind_address}
        if self.config.hostname:
            values.add(self.config.hostname.lower())
        return {item.lower() for item in values}

    def host_allowed(self, host_header: str | None) -> bool:
        if not host_header:
            return False
        host = host_header.strip().lower()
        if host.startswith("["):
            hostname = host.split("]", 1)[0] + "]"
        else:
            hostname = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
        return hostname in self.allowed_hostnames

    @property
    def allowed_origins(self) -> set[str]:
        scheme = "https" if self.config.mode == LAN_HTTPS else "http"
        # Loopback stays reachable in every mode, so its origins have to follow
        # the scheme the server actually serves or same-origin requests from the
        # host machine are rejected.
        values = {
            f"{scheme}://127.0.0.1:{self.config.port}",
            f"{scheme}://localhost:{self.config.port}",
        }
        if self.config.mode == LAN_HTTPS:
            values.add(f"https://{self.config.bind_address}:{self.config.port}")
            if self.config.hostname:
                values.add(f"https://{self.config.hostname}:{self.config.port}")
        return {item.rstrip("/").lower() for item in values}

    def origin_allowed(self, origin: str | None) -> bool:
        if not origin:
            return True
        return origin.rstrip("/").lower() in self.allowed_origins


class FirewallManager:
    def __init__(self, *, executable: str = "powershell.exe") -> None:
        self.executable = executable

    @staticmethod
    def command_for(config: NetworkAccessConfig, *, remove: bool = False) -> list[str]:
        rule = config.firewall.rule_name.replace("'", "''")
        remove_command = f"Get-NetFirewallRule -DisplayName '{rule}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule"
        if remove:
            script = remove_command
        else:
            remotes = ",".join(config.allowed_networks)
            script = (
                f"{remove_command}; "
                f"New-NetFirewallRule -DisplayName '{rule}' -Direction Inbound -Action Allow "
                f"-Protocol TCP -LocalPort {config.port} -Profile Private -RemoteAddress '{remotes}'"
            )
        return ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script]

    def apply(self, config: NetworkAccessConfig, *, remove: bool = False) -> dict[str, Any]:
        argv = [self.executable, *self.command_for(config, remove=remove)]
        if os.name != "nt":
            return {"applied": False, "reason": "Windows-only", "command": argv}
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
        except OSError as exc:
            return {"applied": False, "reason": str(exc), "command": argv}
        return {
            "applied": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
            "command": argv,
        }


def certificate_ssl_context(config: NetworkAccessConfig) -> ssl.SSLContext | None:
    if config.mode != LAN_HTTPS:
        return None
    config.validate(require_files=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(config.tls.certificate_path, config.tls.private_key_path)
    return context


def private_key_is_outside_release(repo_root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(repo_root.resolve())
        return False
    except ValueError:
        return True
