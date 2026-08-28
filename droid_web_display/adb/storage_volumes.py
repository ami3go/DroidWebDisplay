from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath

_ANDROID_VOLUME_RE = re.compile(r"^[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}$")
_BLOCK_HEADER_RE = re.compile(r"^\s*(DiskInfo|VolumeInfo)\{([^}]+)}:\s*$")
_PAIR_RE = re.compile(r"(?<!\S)([A-Za-z][A-Za-z0-9]*)=")
_SHARED_FOLDERS = (
    ("downloads", "Download"),
    ("documents", "Documents"),
    ("pictures", "Pictures"),
    ("dcim", "DCIM"),
    ("movies", "Movies"),
)
_MOUNTED_STATES = frozenset({"MOUNTED", "MOUNTED_READ_ONLY"})


@dataclass(frozen=True)
class AndroidDisk:
    disk_id: str
    flags: frozenset[str]


@dataclass(frozen=True)
class AndroidVolume:
    volume_id: str
    volume_type: str
    disk_id: str | None
    mount_flags: frozenset[str]
    mount_user_id: int | None
    state: str
    fs_uuid: str | None
    fs_label: str | None
    path: str | None


@dataclass(frozen=True)
class AndroidStorageInventory:
    disks: tuple[AndroidDisk, ...]
    volumes: tuple[AndroidVolume, ...]
    primary_storage_uuid: str | None


def _optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return None if normalized in {"", "null"} else normalized


def _flags(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    return frozenset(part.removeprefix("FLAG_") for part in value.split("|") if part and part != "0")


def _integer(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _line_pairs(line: str) -> dict[str, str]:
    matches = list(_PAIR_RE.finditer(line))
    pairs: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        pairs[match.group(1)] = line[match.end() : end].strip()
    return pairs


def parse_storage_manager_dump(text: str) -> AndroidStorageInventory:
    """Parse the stable ``DiskInfo`` and ``VolumeInfo`` fields from ``dumpsys mount``.

    Android prints several key/value pairs on each line and descriptions may
    contain spaces. Splitting on whitespace would therefore corrupt labels and
    can also pair a volume with the wrong path.
    """

    disk_fields: list[tuple[str, dict[str, str]]] = []
    volume_fields: list[tuple[str, dict[str, str]]] = []
    current_kind: str | None = None
    current_id = ""
    current_fields: dict[str, str] = {}
    primary_storage_uuid: str | None = None

    def finish_block() -> None:
        nonlocal current_kind, current_id, current_fields
        if current_kind == "DiskInfo":
            disk_fields.append((current_id, current_fields))
        elif current_kind == "VolumeInfo":
            volume_fields.append((current_id, current_fields))
        current_kind = None
        current_id = ""
        current_fields = {}

    for raw in text.splitlines():
        header = _BLOCK_HEADER_RE.match(raw)
        if header:
            finish_block()
            current_kind, current_id = header.groups()
            continue
        stripped = raw.strip()
        if current_kind is not None and stripped.endswith(":") and "=" not in stripped:
            finish_block()
        if stripped.startswith("Primary storage UUID:"):
            primary_storage_uuid = _optional(stripped.partition(":")[2])
        if current_kind is not None:
            current_fields.update(_line_pairs(raw))
    finish_block()

    disks = tuple(
        AndroidDisk(disk_id=disk_id, flags=_flags(fields.get("flags"))) for disk_id, fields in disk_fields
    )
    volumes = tuple(
        AndroidVolume(
            volume_id=volume_id,
            volume_type=(fields.get("type") or "").removeprefix("TYPE_"),
            disk_id=_optional(fields.get("diskId")),
            mount_flags=_flags(fields.get("mountFlags")),
            mount_user_id=_integer(fields.get("mountUserId")),
            state=(fields.get("state") or "").removeprefix("STATE_"),
            fs_uuid=_optional(fields.get("fsUuid")),
            fs_label=_optional(fields.get("fsLabel")),
            path=_optional(fields.get("path")),
        )
        for volume_id, fields in volume_fields
    )
    return AndroidStorageInventory(disks=disks, volumes=volumes, primary_storage_uuid=primary_storage_uuid)


def _emulated_private_id(volume_id: str) -> str | None:
    base = volume_id.partition(";")[0]
    if base == "emulated":
        return "private"
    if base.startswith("emulated:"):
        return f"private:{base.removeprefix('emulated:')}"
    return None


def _emulated_user_path(volume: AndroidVolume) -> str | None:
    if volume.path is None:
        return None
    path = volume.path.rstrip("/")
    if path == "/storage/emulated":
        return f"{path}/{volume.mount_user_id if volume.mount_user_id is not None else 0}"
    return path


def _canonical_shared_base(path: str) -> str | None:
    normalized = str(PurePosixPath(path))
    if normalized in {"/sdcard", "/mnt/sdcard"}:
        return "/sdcard"
    if re.fullmatch(r"/storage/emulated/\d+", normalized):
        return "/sdcard"
    name = PurePosixPath(normalized).name
    if PurePosixPath(normalized).parent == PurePosixPath("/storage") and _ANDROID_VOLUME_RE.fullmatch(name):
        return normalized
    return None


def _folder_roots(kind: str, base: str) -> list[dict[str, str]]:
    title = "Internal storage" if kind == "internal" else "SD card"
    return [
        {
            "id": f"{kind}-{identifier}",
            "label": f"{title} · {folder}",
            "path": f"{base.rstrip('/')}/{folder}",
        }
        for identifier, folder in _SHARED_FOLDERS
    ]


def storage_roots_from_inventory(inventory: AndroidStorageInventory) -> list[dict[str, str]]:
    """Build Explorer roots from Android's physical-volume classification.

    ``/sdcard`` is only a legacy alias for the *primary shared volume*. It is
    usually backed by built-in storage, but Android also permits a physical or
    adopted SD card to be primary. Disk flags are therefore used for labels;
    path spelling and volume order are never used as storage-type signals.
    """

    disks = {disk.disk_id: disk for disk in inventory.disks}
    private_volumes = {
        volume.volume_id: volume for volume in inventory.volumes if volume.volume_type == "PRIVATE"
    }
    internal_locations: list[str] = []
    sd_locations: list[tuple[str, str | None]] = []
    other_locations: list[tuple[str, str, str | None]] = []

    for volume in inventory.volumes:
        if volume.state not in _MOUNTED_STATES:
            continue
        if volume.volume_type == "EMULATED":
            path = _emulated_user_path(volume)
            base = _canonical_shared_base(path) if path else None
            if base is None:
                continue
            private_id = _emulated_private_id(volume.volume_id)
            private_volume = private_volumes.get(private_id or "")
            backing_disk = disks.get(private_volume.disk_id or "") if private_volume else None
            primary_uuid_matches_sd = bool(
                inventory.primary_storage_uuid
                and private_volume
                and private_volume.fs_uuid
                and inventory.primary_storage_uuid.casefold() == private_volume.fs_uuid.casefold()
                and backing_disk
                and "SD" in backing_disk.flags
            )
            if (
                backing_disk
                and "SD" in backing_disk.flags
                and ("PRIMARY" in volume.mount_flags or primary_uuid_matches_sd)
            ):
                sd_locations.append((base, private_volume.fs_label or private_volume.fs_uuid))
            else:
                internal_locations.append(base)
            continue

        if volume.volume_type not in {"PUBLIC", "STUB"} or volume.path is None:
            continue
        base = _canonical_shared_base(volume.path)
        if base is None:
            continue
        disk = disks.get(volume.disk_id or "")
        disk_flags = disk.flags if disk else frozenset()
        detail = volume.fs_label or volume.fs_uuid
        if "SD" in disk_flags:
            sd_locations.append((base, detail))
        elif "USB" in disk_flags:
            other_locations.append(("usb-storage", base, detail))
        elif "PRIMARY" in volume.mount_flags or "DEFAULT_PRIMARY" in disk_flags:
            internal_locations.append(base)
        else:
            other_locations.append(("external-storage", base, detail))

    roots: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(records: list[dict[str, str]]) -> None:
        for record in records:
            if record["path"] in seen:
                continue
            seen.add(record["path"])
            roots.append(record)

    for base in internal_locations:
        add(_folder_roots("internal", base))
    for base, detail in sd_locations:
        if base == "/sdcard":
            add(_folder_roots("sd-card", base))
            continue
        suffix = f" · {detail}" if detail else ""
        add(
            [
                {
                    "id": f"sd-card-{PurePosixPath(base).name.lower()}",
                    "label": f"SD card{suffix}",
                    "path": base,
                }
            ]
        )
    for kind, base, detail in other_locations:
        title = "USB storage" if kind == "usb-storage" else "External storage"
        suffix = f" · {detail}" if detail else ""
        add([{"id": f"{kind}-{PurePosixPath(base).name.lower()}", "label": f"{title}{suffix}", "path": base}])
    return roots


def storage_roots_from_mount_dump(text: str) -> list[dict[str, str]]:
    return storage_roots_from_inventory(parse_storage_manager_dump(text))
