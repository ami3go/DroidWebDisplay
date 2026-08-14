from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_windows_package_is_windowed_desktop_host() -> None:
    spec = (ROOT / "packaging" / "pyinstaller" / "DroidWebDisplay.spec").read_text(encoding="utf-8")
    assert 'if sys.platform == "win32"' in spec
    windows_section = spec.split('if sys.platform == "win32":', 1)[1].split("else:", 1)[0]
    assert "console=False" in windows_section


def test_package_smoke_uses_headless_mode() -> None:
    smoke = (ROOT / "tools" / "smoke_desktop_package.py").read_text(encoding="utf-8")
    assert '"--headless"' in smoke


def test_qt_essentials_is_a_direct_runtime_dependency() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"PySide6-Essentials==6.11.1"' in pyproject
