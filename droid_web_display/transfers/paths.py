from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

from droid_web_display.errors import TransferValidationError
from droid_web_display.transfers.models import DuplicatePolicy

ANDROID_STORAGE_ROOTS = (
    {"id": "internal-downloads", "label": "Internal storage · Download", "path": "/sdcard/Download"},
    {"id": "internal-documents", "label": "Internal storage · Documents", "path": "/sdcard/Documents"},
    {"id": "internal-pictures", "label": "Internal storage · Pictures", "path": "/sdcard/Pictures"},
    {"id": "internal-dcim", "label": "Internal storage · DCIM", "path": "/sdcard/DCIM"},
    {"id": "internal-movies", "label": "Internal storage · Movies", "path": "/sdcard/Movies"},
)
ANDROID_ALLOWED_ROOTS = tuple(PurePosixPath(item["path"]) for item in ANDROID_STORAGE_ROOTS)
ANDROID_PATH_ALIASES = (
    (PurePosixPath("/storage/emulated/0"), PurePosixPath("/sdcard")),
    (PurePosixPath("/mnt/sdcard"), PurePosixPath("/sdcard")),
)
_EXTERNAL_STORAGE_RE = re.compile(r"^/storage/[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}(?:/.*)?$")
_KNOWN_INTERNAL_CASE = {
    "/sdcard/download": "/sdcard/Download",
    "/sdcard/documents": "/sdcard/Documents",
    "/sdcard/pictures": "/sdcard/Pictures",
    "/sdcard/dcim": "/sdcard/DCIM",
    "/sdcard/movies": "/sdcard/Movies",
}

_WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))
}


def canonicalize_android_path(path: str) -> str:
    if not path or "\x00" in path or "\\" in path:
        raise TransferValidationError("invalid Android path", details={"path": path})
    pure = PurePosixPath(path)
    if not pure.is_absolute() or ".." in pure.parts:
        raise TransferValidationError("Android path must be absolute and must not contain '..'", details={"path": path})
    normalized = PurePosixPath("/", *[part for part in pure.parts if part not in {"/", "."}])
    for alias, canonical in ANDROID_PATH_ALIASES:
        if normalized == alias or alias in normalized.parents:
            relative = normalized.relative_to(alias)
            normalized = canonical / relative
            break
    value = str(normalized)
    lowered = value.lower()
    for alias, canonical in _KNOWN_INTERNAL_CASE.items():
        if lowered == alias or lowered.startswith(alias + "/"):
            value = canonical + value[len(alias):]
            break
    media_rw = re.match(r"^/mnt/media_rw/([0-9A-Fa-f]{4}-[0-9A-Fa-f]{4})(/.*)?$", value)
    if media_rw:
        value = f"/storage/{media_rw.group(1)}{media_rw.group(2) or ''}"
    return value


def is_allowed_android_path(path: PurePosixPath) -> bool:
    value = str(path)
    return any(path == root or root in path.parents for root in ANDROID_ALLOWED_ROOTS) or bool(_EXTERNAL_STORAGE_RE.fullmatch(value))


def normalize_android_path(path: str, *, require_allowed: bool = True) -> str:
    normalized = PurePosixPath(canonicalize_android_path(path))
    if require_allowed and not is_allowed_android_path(normalized):
        raise TransferValidationError(
            "Android path is outside the allowed shared-storage roots",
            details={"path": str(normalized), "allowedRoots": [str(root) for root in ANDROID_ALLOWED_ROOTS] + ["/storage/<XXXX-XXXX>"]},
        )
    return str(normalized)


def is_android_storage_root(path: str) -> bool:
    """Return whether *path* is a protected Explorer storage root.

    Explorer operations may work below the configured shared-storage roots,
    but deleting a root such as ``/sdcard/Download`` or an adopted-storage
    volume would be far broader than deleting a selected row.
    """
    normalized = PurePosixPath(normalize_android_path(path))
    if normalized in ANDROID_ALLOWED_ROOTS:
        return True
    return normalized.parent == PurePosixPath("/storage") and bool(
        re.fullmatch(r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}", normalized.name)
    )


def storage_root_list() -> list[dict[str, str]]:
    return [dict(item) for item in ANDROID_STORAGE_ROOTS]


def join_android_path(directory: str, filename: str) -> str:
    directory = normalize_android_path(directory)
    safe_name = sanitize_filename(filename)
    return normalize_android_path(str(PurePosixPath(directory) / safe_name))


def sanitize_filename(filename: str) -> str:
    value = Path(filename).name.strip().rstrip(". ")
    value = _WINDOWS_INVALID.sub("_", value)
    if not value:
        value = "file"
    stem = Path(value).stem.upper()
    if stem in _WINDOWS_RESERVED:
        value = f"_{value}"
    return value[:240]


def resolve_duplicate(path: Path, policy: DuplicatePolicy) -> Path:
    if not path.exists() or policy == DuplicatePolicy.OVERWRITE:
        return path
    if policy == DuplicatePolicy.FAIL:
        raise FileExistsError(os.fspath(path))
    stem, suffix = path.stem, path.suffix
    for index in range(1, 10_000):
        candidate = path.with_name(f"{stem} ({index}){suffix}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"unable to resolve duplicate filename for {path}")
