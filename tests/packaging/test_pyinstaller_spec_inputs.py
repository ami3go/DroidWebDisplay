"""Behavioural coverage for the shared PyInstaller spec inputs.

These execute _dwd_common rather than grepping the specs, so a spec that stops
bundling a file fails here instead of passing a source-text match.
"""

from pathlib import Path
import importlib.util
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "packaging" / "pyinstaller" / "_dwd_common.py"


def _load():
    pytest.importorskip("PyInstaller", reason="PyInstaller is only installed in the packaging jobs")
    spec = importlib.util.spec_from_file_location("_dwd_common_under_test", COMMON)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_version_parsing_accepts_prerelease_and_rejects_garbage() -> None:
    common = _load()
    text, numeric = common.read_version(ROOT)
    assert text == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert len(numeric) == 4 and all(isinstance(part, int) for part in numeric)
    assert numeric[3] == 0


def test_bundled_data_covers_every_runtime_asset(tmp_path: Path) -> None:
    common = _load()
    destinations = {destination for _, destination in common.bundle_datas(ROOT)}
    # A file dropped from this list yields a package that starts and then fails
    # at runtime, so assert the whole set rather than a sample.
    assert destinations == {
        "apps/web-client/dist",
        "apps/web-client",
        "packages/scrcpy-protocol/dist",
        "packages/scrcpy-protocol",
        "compatibility",
        "server",
        ".",
    }
    for source, _ in common.bundle_datas(ROOT):
        assert Path(source).exists(), f"spec bundles a missing path: {source}"


def test_adb_discovery_requires_the_executable(tmp_path: Path) -> None:
    common = _load()
    (tmp_path / "AdbWinApi.dll").write_bytes(b"x")
    # DLLs alone must not satisfy the check: the package would look complete and
    # then fail the moment a user plugs in a phone.
    with pytest.raises(SystemExit):
        common.adb_binaries(tmp_path, windows=True)
    (tmp_path / "adb.exe").write_bytes(b"x")
    assert len(common.adb_binaries(tmp_path, windows=True)) == 2
    with pytest.raises(SystemExit):
        common.adb_binaries(tmp_path, windows=False)
    (tmp_path / "adb").write_bytes(b"x")
    assert len(common.adb_binaries(tmp_path, windows=False)) == 1
