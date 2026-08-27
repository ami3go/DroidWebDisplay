from __future__ import annotations

import re

_PACKAGE_PATTERN = r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+"
_PACKAGE_RE = re.compile(rf"^{_PACKAGE_PATTERN}$")
_LABELED_APP_RE = re.compile(rf"^(?P<label>.+?)\s+(?P<package>{_PACKAGE_PATTERN})\s*$")
_SERVER_LOG_PREFIX_RE = re.compile(r"^\[server\]\s+[A-Z]+:\s?")
_APP_LIST_HEADER = "List of apps:"
_APP_MARKERS = (" * ", " - ")


def fallback_app_label(package_name: str) -> str:
    """Return a readable last-resort label when Android cannot resolve one."""

    if package_name == "com.openai.chatgpt":
        return "ChatGPT"
    leaf = package_name.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ").strip()
    return leaf.title() or package_name


def normalize_app_label(value: str, package_name: str) -> str:
    """Keep Android's localized label while making it safe for a one-line menu."""

    normalized = " ".join(value.split())
    return normalized or fallback_app_label(package_name)


def _without_server_prefix(line: str) -> str:
    return _SERVER_LOG_PREFIX_RE.sub("", line, count=1)


def parse_scrcpy_app_list(text: str) -> dict[str, str]:
    """Parse the official scrcpy ``list_apps`` output into package labels.

    scrcpy resolves each label with Android's PackageManager. Names up to 30
    UTF-16 code units share a line with their package; longer names put the
    package on the following indented line. Both forms are accepted here.
    """

    lines = text.splitlines()
    labels: dict[str, str] = {}
    in_app_list = False
    index = 0

    while index < len(lines):
        raw = _without_server_prefix(lines[index].rstrip("\r"))
        if not in_app_list:
            if raw.strip() == _APP_LIST_HEADER:
                in_app_list = True
            index += 1
            continue

        if not raw.startswith(_APP_MARKERS):
            index += 1
            continue

        android_label = raw[3:].strip()

        # LogUtils wraps long labels and prints the package alone on a line
        # indented to the same fixed column as an ordinary package value.
        if index + 1 < len(lines):
            following = _without_server_prefix(lines[index + 1].rstrip("\r"))
            following_package = following.strip()
            if following[:1].isspace() and _PACKAGE_RE.fullmatch(following_package):
                labels.setdefault(
                    following_package,
                    normalize_app_label(android_label, following_package),
                )
                index += 2
                continue

        match = _LABELED_APP_RE.fullmatch(android_label)
        if match:
            package_name = match.group("package")
            labels.setdefault(
                package_name,
                normalize_app_label(match.group("label"), package_name),
            )
        index += 1

    return labels
