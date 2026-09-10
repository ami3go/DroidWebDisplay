import pytest

from droid_web_display.adb.client import AdbClient, AdbCommandResult
from droid_web_display.adb.media_store import AndroidMediaFile, parse_media_store_images


def test_media_store_parser_preserves_commas_and_ignores_invalid_rows() -> None:
    output = """\
Row: 0 _data=/storage/emulated/0/DCIM/Camera/IMG, summer.jpg, _size=2048, date_modified=200
Row: 1 _data=/storage/emulated/0/Pictures/shot.png, _size=1024, date_modified=100
Row: 2 _data=NULL, _size=NULL, date_modified=NULL
Row: 3 _data=relative.jpg, _size=10, date_modified=50
"""

    assert parse_media_store_images(output) == [
        AndroidMediaFile("/storage/emulated/0/DCIM/Camera/IMG, summer.jpg", 2048, 200),
        AndroidMediaFile("/storage/emulated/0/Pictures/shot.png", 1024, 100),
    ]


def test_media_store_parser_deduplicates_and_obeys_limit() -> None:
    output = """\
Row: 0 _data=/sdcard/DCIM/a.jpg, _size=3, date_modified=30
Row: 1 _data=/sdcard/DCIM/a.jpg, _size=3, date_modified=30
Row: 2 _data=/sdcard/DCIM/b.jpg, _size=2, date_modified=20
"""

    assert parse_media_store_images(output, limit=1) == [
        AndroidMediaFile("/sdcard/DCIM/a.jpg", 3, 30),
    ]


@pytest.mark.asyncio
async def test_adb_client_uses_bounded_metadata_only_media_store_query(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AdbClient("adb")
    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    async def fake_shell(serial: str, *args: str, **kwargs: object) -> AdbCommandResult:
        calls.append(((serial, *args), kwargs))
        return AdbCommandResult(
            ("adb",),
            0,
            "Row: 0 _data=/sdcard/DCIM/latest.jpg, _size=12, date_modified=34\n",
            "",
        )

    monkeypatch.setattr(client, "shell", fake_shell)

    assert await client.list_recent_pictures("PHONE", limit=50) == [
        AndroidMediaFile("/sdcard/DCIM/latest.jpg", 12, 34),
    ]
    args, kwargs = calls[0]
    assert args == (
        "PHONE",
        "content",
        "query",
        "--uri",
        "content://media/external/images/media?limit=200",
        "--projection",
        "_data:_size:date_modified",
        "--sort",
        "date_modified DESC",
    )
    assert kwargs == {"check": False, "timeout": 30.0}
