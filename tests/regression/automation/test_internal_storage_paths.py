from droid_web_display.transfers.paths import normalize_android_path, storage_root_list


def test_internal_storage_download_alias_is_supported() -> None:
    assert normalize_android_path("/storage/emulated/0/Download/example.txt") == "/sdcard/Download/example.txt"
    roots = storage_root_list()
    assert roots[0] == {"id": "internal-downloads", "label": "Internal storage · Download", "path": "/sdcard/Download"}
