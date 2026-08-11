from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from droid_web_display.api.app import create_app
from droid_web_display.auth import AuthService
from droid_web_display.config import BridgeConfig
from droid_web_display.network_access import (
    FirewallManager,
    LAN_HTTPS,
    NetworkAccessConfig,
    NetworkAccessError,
    NetworkConfigStore,
    NetworkPolicy,
    TlsSettings,
    generate_certificate,
    validate_certificate_pair,
)
from tests.security.test_api import FakeAdb, FakeSessionManager, FakeSync
from droid_web_display.transfers.manager import TransferManager


def test_local_only_is_default_and_public_or_wildcard_bind_is_rejected(tmp_path: Path) -> None:
    store = NetworkConfigStore(tmp_path / "network-access.json")
    assert store.load().mode == "local-only"
    assert store.load().bind_address == "127.0.0.1"
    with pytest.raises(NetworkAccessError):
        NetworkAccessConfig(mode=LAN_HTTPS, bind_address="0.0.0.0", allowed_networks=("192.168.1.0/24",), tls=TlsSettings(enabled=True)).validate()
    with pytest.raises(NetworkAccessError):
        NetworkAccessConfig(mode=LAN_HTTPS, bind_address="8.8.8.8", allowed_networks=("192.168.1.0/24",), tls=TlsSettings(enabled=True)).validate()


def test_certificate_generation_pair_validation_and_san(tmp_path: Path) -> None:
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    result = generate_certificate(cert, key, bind_address="192.168.50.20", hostname="bridge-pc", validity_days=90)
    assert "192.168.50.20" in result["ipAddresses"]
    assert "127.0.0.1" in result["ipAddresses"]
    assert "bridge-pc" in result["dnsNames"]
    verified = validate_certificate_pair(cert, key, bind_address="192.168.50.20", hostname="bridge-pc")
    assert verified["sha256"] == result["sha256"]
    assert key.read_text(encoding="utf-8").startswith("-----BEGIN PRIVATE KEY-----")


def test_network_policy_restricts_clients_hosts_and_origins(tmp_path: Path) -> None:
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    generate_certificate(cert, key, bind_address="192.168.50.20")
    config = NetworkAccessConfig(
        mode=LAN_HTTPS,
        bind_address="192.168.50.20",
        port=8765,
        allowed_networks=("192.168.50.0/24", "192.168.60.10/32"),
        tls=TlsSettings(enabled=True, certificate_path=str(cert), private_key_path=str(key)),
    ).validate(require_files=True)
    policy = NetworkPolicy(config)
    assert policy.client_allowed("192.168.50.45")
    assert policy.client_allowed("192.168.60.10")
    assert not policy.client_allowed("192.168.61.10")
    assert policy.host_allowed("192.168.50.20:8765")
    assert not policy.host_allowed("evil.example:8765")
    assert policy.origin_allowed("https://192.168.50.20:8765")
    assert not policy.origin_allowed("https://evil.example")


def test_firewall_command_is_private_profile_and_reversible(tmp_path: Path) -> None:
    config = NetworkAccessConfig(
        mode=LAN_HTTPS,
        bind_address="192.168.50.20",
        port=8765,
        allowed_networks=("192.168.50.0/24",),
        tls=TlsSettings(enabled=True),
    )
    create = " ".join(FirewallManager.command_for(config))
    remove = " ".join(FirewallManager.command_for(config, remove=True))
    assert "-Profile Private" in create
    assert "-LocalPort 8765" in create
    assert "192.168.50.0/24" in create
    assert "Remove-NetFirewallRule" in remove
    assert "New-NetFirewallRule" not in remove


def _network_app(tmp_path: Path):
    adb = FakeAdb()
    transfers = TransferManager(
        adb,
        FakeSync(),
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
    )  # type: ignore[arg-type]
    config = BridgeConfig(
        repo_root=Path(__file__).resolve().parents[2],
        transfer_data_directory=tmp_path / "data",
        default_download_directory=tmp_path / "downloads",
        authentication_required=True,
        auth_data_file=tmp_path / "data" / "auth.json",
        network_config_file=tmp_path / "data" / "network-access.json",
    )
    return create_app(
        config=config,
        manager=FakeSessionManager(),  # type: ignore[arg-type]
        adb=adb,  # type: ignore[arg-type]
        transfers=transfers,
        auth=AuthService(config.resolved_auth_data_file),
    )


def test_network_api_requires_pin_validates_and_persists_lan_config(tmp_path: Path) -> None:
    app = _network_app(tmp_path)
    with TestClient(app) as client:
        setup = client.post("/api/v1/auth/setup", json={"pin": "123456", "confirmPin": "123456", "duration": "1-day"})
        csrf = setup.json()["csrfToken"]
        payload = {
            "mode": "lan-https",
            "bindAddress": "192.168.50.20",
            "port": 8765,
            "allowedNetworks": ["192.168.50.0/24"],
            "hostname": "bridge-pc",
            "certificateSource": "generated",
            "certificateValidityDays": 90,
            "manageFirewall": False,
            "currentPin": "123456",
        }
        denied = client.post("/api/v1/network/validate", json={**payload, "currentPin": "0000"}, headers={"x-droidwebdisplay-csrf": csrf})
        assert denied.status_code == 401
        valid = client.post("/api/v1/network/validate", json=payload, headers={"x-droidwebdisplay-csrf": csrf})
        assert valid.status_code == 200, valid.text
        applied = client.post("/api/v1/network/apply", json=payload, headers={"x-droidwebdisplay-csrf": csrf})
        assert applied.status_code == 200, applied.text
        assert applied.json()["url"] == "https://bridge-pc:8765"
        saved = NetworkConfigStore(tmp_path / "data" / "network-access.json").load()
        assert saved.mode == LAN_HTTPS
        assert Path(saved.tls.certificate_path or "").is_file()
        assert Path(saved.tls.private_key_path or "").is_file()
        assert client.get("/api/v1/devices").status_code == 401  # sessions revoked after trust-boundary change


def test_lan_cookie_is_secure_after_local_pin_bootstrap(tmp_path: Path) -> None:
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    generate_certificate(cert, key, bind_address="192.168.50.20")
    config = BridgeConfig(
        repo_root=Path(__file__).resolve().parents[2],
        transfer_data_directory=tmp_path / "data",
        auth_data_file=tmp_path / "data" / "auth.json",
        network_config_file=tmp_path / "data" / "network-access.json",
        network_mode=LAN_HTTPS,
        bind_host="192.168.50.20",
        bind_port=8765,
        allowed_client_networks=("192.168.50.0/24",),
        tls_enabled=True,
        tls_certificate_path=cert,
        tls_private_key_path=key,
    )
    auth = AuthService(config.resolved_auth_data_file)
    auth.setup(
        "123456",
        duration="1-day",
        custom_seconds=None,
        user_agent="local bootstrap",
        access_mode="local",
    )
    app = create_app(config=config, manager=FakeSessionManager(), adb=FakeAdb(), auth=auth)  # type: ignore[arg-type]
    with TestClient(app, base_url="https://192.168.50.20:8765") as client:
        response = client.post("/api/v1/auth/login", json={"pin": "123456", "duration": "1-day"})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert "secure" in cookie
        assert "httponly" in cookie
        assert "samesite=strict" in cookie
