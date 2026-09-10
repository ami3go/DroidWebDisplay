from __future__ import annotations

from droid_web_display.adb.storage_volumes import (
    parse_storage_manager_dump,
    storage_roots_from_mount_dump,
)

STANDARD_VOLUME_DUMP = """Disks:
  DiskInfo{disk:179,0}:
    flags=ADOPTABLE|SD size=128000000000 label=Samsung SD
    sysPath=/sys/devices/platform/sdhci
Volumes:
  VolumeInfo{public:179,1}:
    type=PUBLIC diskId=disk:179,0 partGuid=null mountFlags=VISIBLE_FOR_READ|VISIBLE_FOR_WRITE mountUserId=0 state=MOUNTED
    fsType=exfat fsUuid=1234-ABCD fsLabel=Samsung Card
    path=/storage/1234-ABCD internalPath=/mnt/media_rw/1234-ABCD
  VolumeInfo{private}:
    type=PRIVATE diskId=null partGuid=null mountFlags=0 mountUserId=-10000 state=MOUNTED
    fsType=ext4 fsUuid=null fsLabel=null
    path=/data internalPath=null
  VolumeInfo{emulated;0}:
    type=EMULATED diskId=null partGuid=null mountFlags=PRIMARY|VISIBLE_FOR_READ|VISIBLE_FOR_WRITE mountUserId=0 state=MOUNTED
    fsType=null fsUuid=null fsLabel=null
    path=/storage/emulated internalPath=/data/media
Records:
  VolumeRecord{unexpected-record}:
    fsUuid=FFFF-EEEE fsLabel=Must Not Replace The Last Volume
Primary storage UUID: null
"""


PRIMARY_SD_VOLUME_DUMP = """Disks:
  DiskInfo{disk:8,0}:
    flags=DEFAULT_PRIMARY size=64000000000 label=Built-in shared storage
    sysPath=/sys/devices/platform/internal
  DiskInfo{disk:179,0}:
    flags=ADOPTABLE|SD size=128000000000 label=Samsung SD
    sysPath=/sys/devices/platform/sdhci
Volumes:
  VolumeInfo{emulated:179,2;0}:
    type=EMULATED diskId=null partGuid=null mountFlags=PRIMARY|VISIBLE_FOR_READ|VISIBLE_FOR_WRITE mountUserId=0 state=MOUNTED
    fsType=null fsUuid=null fsLabel=null
    path=/storage/emulated internalPath=/mnt/expand/5E6F-7A8B/media
  VolumeInfo{private:179,2}:
    type=PRIVATE diskId=disk:179,0 partGuid=null mountFlags=0 mountUserId=-10000 state=MOUNTED
    fsType=ext4 fsUuid=5E6F-7A8B fsLabel=Portable SD
    path=/mnt/expand/5E6F-7A8B internalPath=null
  VolumeInfo{public:8,1}:
    type=PUBLIC diskId=disk:8,0 partGuid=null mountFlags=VISIBLE_FOR_READ|VISIBLE_FOR_WRITE mountUserId=0 state=MOUNTED
    fsType=exfat fsUuid=1A2B-3C4D fsLabel=Phone storage
    path=/storage/1A2B-3C4D internalPath=/mnt/media_rw/1A2B-3C4D
Primary storage UUID: 5E6F-7A8B
"""


def test_storage_dump_keeps_volume_labels_and_fields_together() -> None:
    inventory = parse_storage_manager_dump(STANDARD_VOLUME_DUMP)

    assert inventory.primary_storage_uuid is None
    assert inventory.disks[0].flags == frozenset({"ADOPTABLE", "SD"})
    assert inventory.volumes[0].volume_id == "public:179,1"
    assert inventory.volumes[0].fs_label == "Samsung Card"
    assert inventory.volumes[-1].fs_uuid is None


def test_standard_android_mapping_labels_emulated_as_internal_and_public_sd_as_sd_card() -> None:
    roots = storage_roots_from_mount_dump(STANDARD_VOLUME_DUMP)

    assert roots[0] == {
        "id": "internal-downloads",
        "label": "Internal storage · Download",
        "path": "/sdcard/Download",
    }
    assert {
        "id": "sd-card-1234-abcd",
        "label": "SD card · Samsung Card",
        "path": "/storage/1234-ABCD",
    } in roots


def test_primary_sd_mapping_does_not_invert_internal_and_sd_card_paths() -> None:
    roots = storage_roots_from_mount_dump(PRIMARY_SD_VOLUME_DUMP)
    by_label = {root["label"]: root["path"] for root in roots}

    assert by_label["Internal storage · Download"] == "/storage/1A2B-3C4D/Download"
    assert by_label["SD card · Download"] == "/sdcard/Download"
    assert by_label["Internal storage · Download"] != by_label["SD card · Download"]
