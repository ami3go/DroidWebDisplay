from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_linux_installer_has_no_rsync_dependency_and_preserves_state() -> None:
    text = (ROOT / "packaging/linux/install.sh").read_text(encoding="utf-8")
    assert "rsync -" not in text
    assert 'preserve = {"data", "downloads", "logs", ".venv"}' in text
    assert "systemctl --user stop gpt-bridge.service" in text
    assert "stop_bridge_service.py" in text


def test_windows_installer_stops_old_service_and_preserves_state() -> None:
    text = (ROOT / "packaging/windows/install.ps1").read_text(encoding="utf-8")
    assert "stop_bridge_service.py" in text
    assert '@("data", "downloads", "logs")' in text
    assert '".venv"' in text


def test_only_templated_linux_systemd_unit_is_packaged() -> None:
    assert (ROOT / "packaging/linux/gpt-bridge.service.in").is_file()
    assert not (ROOT / "packaging/linux/gpt-bridge.service").exists()
