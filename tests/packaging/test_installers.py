from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def test_linux_installer_has_no_rsync_dependency_and_preserves_state() -> None:
    text = (ROOT / "packaging/linux/install.sh").read_text(encoding="utf-8")
    assert "rsync -" not in text
    assert 'data|downloads|logs|.venv' in text
    assert "systemctl --user stop droidwebdisplay.service" in text
    assert "stop_bridge_service.py" in text


def test_linux_installer_with_bundled_runtime_does_not_require_host_python(tmp_path: Path) -> None:
    release = tmp_path / "release"
    linux = release / "packaging/linux"
    linux.mkdir(parents=True)
    shutil.copy2(ROOT / "packaging/linux/install.sh", linux / "install.sh")
    for name in ("droidwebdisplay.service.in", "droidwebdisplay.desktop.in", "droidwebdisplay.svg"):
        shutil.copy2(ROOT / "packaging/linux" / name, linux / name)
    (release / "DroidWebDisplay.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    bundled = release / "runtime/python/bin/python3"
    bundled.parent.mkdir(parents=True)
    bundled.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    bundled.chmod(0o755)

    shims = tmp_path / "shims"
    shims.mkdir()
    marker = tmp_path / "host-python-called"
    host_python = shims / "python3"
    host_python.write_text(
        f"#!/usr/bin/env bash\nprintf called > {marker!s}\nexit 97\n",
        encoding="utf-8",
    )
    host_python.chmod(0o755)

    home = tmp_path / "home"
    install_root = tmp_path / "installed"
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{shims}{os.pathsep}{env.get('PATH', '')}",
            "DROID_WEB_DISPLAY_INSTALL_ROOT": str(install_root),
            "XDG_BIN_HOME": str(home / ".local/bin"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
        }
    )
    result = subprocess.run(
        ["bash", str(linux / "install.sh")],
        cwd=release,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not marker.exists(), "installer invoked host python3 despite a bundled runtime"
    assert (install_root / "runtime/python/bin/python3").is_file()


def test_windows_installer_stops_old_service_and_preserves_state() -> None:
    text = (ROOT / "packaging/windows/install.ps1").read_text(encoding="utf-8")
    assert "stop_bridge_service.py" in text
    assert '@("data", "downloads", "logs")' in text
    assert '".venv"' in text


def test_only_templated_linux_systemd_unit_is_packaged() -> None:
    assert (ROOT / "packaging/linux/droidwebdisplay.service.in").is_file()
    assert not (ROOT / "packaging/linux/droidwebdisplay.service").exists()
