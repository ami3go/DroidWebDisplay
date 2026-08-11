from pathlib import Path

import pytest

from droid_web_display.errors import TransferValidationError
from droid_web_display.transfers.models import DuplicatePolicy
from droid_web_display.transfers.paths import join_android_path, normalize_android_path, resolve_duplicate, sanitize_filename


def test_android_paths_are_restricted_to_shared_storage() -> None:
    assert normalize_android_path("/sdcard/Download/file.txt") == "/sdcard/Download/file.txt"
    assert join_android_path("/sdcard/Documents", "report.pdf") == "/sdcard/Documents/report.pdf"
    with pytest.raises(TransferValidationError):
        normalize_android_path("/data/data/com.openai.chatgpt/private")
    with pytest.raises(TransferValidationError):
        normalize_android_path("/sdcard/Download/../secret")


def test_filename_sanitization_and_duplicate_resolution(tmp_path: Path) -> None:
    assert sanitize_filename('CON?.txt') == 'CON_.txt'
    target = tmp_path / "result.zip"
    target.write_bytes(b"one")
    assert resolve_duplicate(target, DuplicatePolicy.RENAME).name == "result (1).zip"
    assert resolve_duplicate(target, DuplicatePolicy.OVERWRITE) == target
    with pytest.raises(FileExistsError):
        resolve_duplicate(target, DuplicatePolicy.FAIL)
