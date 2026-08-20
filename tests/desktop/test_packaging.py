from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_windows_package_is_windowed_desktop_host() -> None:
    """Both Windows packages must launch without a console window.

    This used to read the win32 branch of DroidWebDisplay.spec, a branch CI
    never reached and which built an exe with no icon and no version resource.
    Removing that dead code broke this test, which is to say the test existed
    to protect it. The property it is named for belongs to the specs Windows
    actually builds.
    """
    for name in ("DroidWebDisplayWindows.spec", "DroidWebDisplayWindowsOnedir.spec"):
        spec = (ROOT / "packaging" / "pyinstaller" / name).read_text(encoding="utf-8")
        assert "console=False" in spec, name
        assert "console=True" not in spec, name

    linux = (ROOT / "packaging" / "pyinstaller" / "DroidWebDisplay.spec").read_text(encoding="utf-8")
    assert "DroidWebDisplayWindows.spec" in linux, "the Linux spec must redirect Windows builds"


def test_package_smoke_uses_headless_mode() -> None:
    smoke = (ROOT / "tools" / "smoke_desktop_package.py").read_text(encoding="utf-8")
    assert '"--headless"' in smoke


def test_qt_essentials_is_a_direct_runtime_dependency() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"PySide6-Essentials==6.11.1"' in pyproject
