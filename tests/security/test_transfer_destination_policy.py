from __future__ import annotations

from pathlib import Path

import pytest

from droid_web_display.errors import TransferValidationError
from droid_web_display.transfers.manager import TransferManager


class DummyAdb:
    pass


class DummySync:
    pass


def manager_for(tmp_path: Path) -> TransferManager:
    return TransferManager(
        DummyAdb(),  # type: ignore[arg-type]
        DummySync(),  # type: ignore[arg-type]
        data_directory=tmp_path / "data",
        destination_profiles={"default-downloads": tmp_path / "downloads"},
    )


def test_custom_destination_must_stay_inside_approved_profile(tmp_path: Path) -> None:
    manager = manager_for(tmp_path)
    root = (tmp_path / "downloads").resolve()
    assert manager._custom_destination(str(root)) == root
    assert manager._custom_destination(str(root / "reports")) == root / "reports"

    with pytest.raises(TransferValidationError, match="approved destination profile"):
        manager._custom_destination(str(tmp_path / "elsewhere"))


def test_custom_destination_resolves_symlinks_before_profile_check(tmp_path: Path) -> None:
    manager = manager_for(tmp_path)
    root = tmp_path / "downloads"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable on this platform")

    with pytest.raises(TransferValidationError, match="approved destination profile"):
        manager._custom_destination(str(link / "payload"))
