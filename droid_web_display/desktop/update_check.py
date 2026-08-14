from __future__ import annotations

from dataclasses import dataclass
import json
import re
from urllib.request import Request, urlopen

RELEASES_URL = "https://api.github.com/repos/ami3go/DroidWebDisplay/releases?per_page=30"
_VERSION_RE = re.compile(
    r"(?<!\d)(\d+)\.(\d+)\.(\d+)(?:[-._]?(alpha|a|beta|b|rc)[.-]?(\d+))?",
    re.IGNORECASE,
)
_PRERELEASE_RANK = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2}


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    name: str
    url: str
    prerelease: bool
    version: str


def _version_parts(value: str) -> tuple[tuple[int, int, int, int, int], str]:
    match = _VERSION_RE.search(value)
    if match is None:
        raise ValueError(f"Could not parse version from {value!r}")
    major, minor, patch = (int(match.group(index)) for index in (1, 2, 3))
    prerelease = (match.group(4) or "").casefold()
    prerelease_number = int(match.group(5) or 0)
    if prerelease:
        rank = _PRERELEASE_RANK[prerelease]
        canonical = "a" if prerelease in {"a", "alpha"} else "b" if prerelease in {"b", "beta"} else "rc"
        normalized = f"{major}.{minor}.{patch}{canonical}{prerelease_number}"
    else:
        rank = 3
        prerelease_number = 0
        normalized = f"{major}.{minor}.{patch}"
    return (major, minor, patch, rank, prerelease_number), normalized


def normalize_release_version(value: str) -> str:
    return _version_parts(value)[1]


def is_newer_release(current_version: str, release_tag: str) -> bool:
    current_key, _current = _version_parts(current_version)
    release_key, _release = _version_parts(release_tag)
    return release_key > current_key


def check_latest_release(channel: str, *, timeout: float = 5.0) -> ReleaseInfo:
    normalized_channel = channel.casefold()
    if normalized_channel not in {"stable", "pre-release"}:
        raise ValueError(f"Unsupported release channel: {channel}")

    request = Request(
        RELEASES_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "DroidWebDisplay",
        },
    )
    with urlopen(request, timeout=timeout) as response:  # nosec B310 - fixed HTTPS GitHub endpoint
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError("GitHub returned an unexpected release response")

    candidates: list[tuple[tuple[int, int, int, int, int], ReleaseInfo]] = []
    include_prerelease = normalized_channel == "pre-release"
    for item in payload:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        prerelease = bool(item.get("prerelease"))
        if prerelease and not include_prerelease:
            continue
        tag = str(item.get("tag_name") or "").strip()
        url = str(item.get("html_url") or "").strip()
        if not tag or not url:
            continue
        try:
            version_key, version = _version_parts(tag)
        except ValueError:
            continue
        candidates.append(
            (
                version_key,
                ReleaseInfo(
                    tag=tag,
                    name=str(item.get("name") or tag),
                    url=url,
                    prerelease=prerelease,
                    version=version,
                ),
            )
        )

    if not candidates:
        raise RuntimeError(f"No {channel} release was found")
    return max(candidates, key=lambda candidate: candidate[0])[1]
