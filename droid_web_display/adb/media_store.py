from __future__ import annotations

import re
from dataclasses import dataclass

_ROW_PREFIX_RE = re.compile(r"^Row:\s+\d+\s+_data=(.*)$")


@dataclass(frozen=True)
class AndroidMediaFile:
    path: str
    size: int
    modified_at: int


def parse_media_store_images(text: str, *, limit: int = 50) -> list[AndroidMediaFile]:
    """Parse metadata emitted by Android's ``content query`` command.

    ``_data`` is parsed from the left while the numeric fields are split from
    the right. This preserves valid filenames containing commas without
    treating the command's human-readable output as a shell command.
    """

    if limit < 1:
        return []
    images: list[AndroidMediaFile] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        prefix, modified_separator, modified_raw = raw.rpartition(", date_modified=")
        if not modified_separator:
            continue
        data_part, size_separator, size_raw = prefix.rpartition(", _size=")
        if not size_separator:
            continue
        match = _ROW_PREFIX_RE.match(data_part)
        if match is None:
            continue
        path = match.group(1).strip()
        try:
            size = int(size_raw.strip())
            modified_at = int(modified_raw.strip())
        except ValueError:
            continue
        if not path.startswith("/") or "\x00" in path or size < 0 or modified_at < 0 or path in seen:
            continue
        seen.add(path)
        images.append(AndroidMediaFile(path=path, size=size, modified_at=modified_at))
        if len(images) >= limit:
            break
    return images
