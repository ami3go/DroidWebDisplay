from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .app_labels import fallback_app_label, normalize_app_label

_PACKAGE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+$")
_COMPONENT_RE = re.compile(
    r"(?P<package>[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+)/"
    r"(?P<activity>[A-Za-z0-9_.$]+)"
)
_TASK_ID_PATTERNS = (
    re.compile(r"\bTask\{[^\n]*?\s#(?P<id>\d+)\b"),
    re.compile(r"\btaskId[=:](?P<id>\d+)\b", re.IGNORECASE),
    re.compile(r"\bt(?P<id>\d+)\b"),
)
_DISPLAY_PATTERNS = (
    re.compile(r"\bdisplayId[=:](?P<id>\d+)\b", re.IGNORECASE),
    re.compile(r"\bmDisplayId[=:](?P<id>\d+)\b"),
)
_VISIBLE_RE = re.compile(r"\bvisible(?:Requested)?=(?P<value>true|false)\b", re.IGNORECASE)
_DISPLAY_HEADER_RE = re.compile(r"^\s*Display\s+#(?P<id>\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class RunningGuiApp:
    task_id: int
    package_name: str
    component_name: str
    display_id: int | None
    visible: bool
    resumed: bool
    label: str

    def to_dict(self) -> dict[str, object]:
        return {
            "taskId": self.task_id,
            "packageName": self.package_name,
            "componentName": self.component_name,
            "displayId": self.display_id,
            "visible": self.visible,
            "resumed": self.resumed,
            "label": self.label,
            "hasGui": True,
        }


def validate_component_name(value: str) -> str:
    match = _COMPONENT_RE.fullmatch(value)
    if not match:
        raise ValueError("Invalid Android activity component")
    package = match.group("package")
    if not _PACKAGE_RE.fullmatch(package):
        raise ValueError("Invalid Android package name")
    return value


def _task_id(line: str) -> int | None:
    for pattern in _TASK_ID_PATTERNS:
        match = pattern.search(line)
        if match:
            return int(match.group("id"))
    return None


def _display_id(line: str) -> int | None:
    for pattern in _DISPLAY_PATTERNS:
        match = pattern.search(line)
        if match:
            return int(match.group("id"))
    return None


def parse_running_gui_apps(
    text: str,
    application_labels: Mapping[str, str] | None = None,
) -> list[RunningGuiApp]:
    """Parse GUI tasks from ``dumpsys activity activities`` output.

    Android and vendor builds vary in whitespace and in whether display/task
    identifiers are repeated on every ActivityRecord. The parser therefore
    keeps the nearest Display/Task context and merges repeated records by task.
    Only records with a concrete activity component are returned.
    """

    current_display: int | None = None
    current_task: int | None = None
    tasks: dict[int, dict[str, object]] = {}

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        display_header = _DISPLAY_HEADER_RE.match(raw)
        if display_header:
            current_display = int(display_header.group("id"))
            current_task = None
            continue

        explicit_display = _display_id(line)
        if explicit_display is not None:
            current_display = explicit_display

        task_id = _task_id(line)
        if "Task{" in line and task_id is not None:
            current_task = task_id
            item = tasks.setdefault(task_id, {})
            item.setdefault("display_id", current_display)
            if explicit_display is not None:
                item["display_id"] = explicit_display
            visible = _VISIBLE_RE.search(line)
            if visible:
                item["visible"] = visible.group("value").lower() == "true"
            task_type = re.search(r"\btype=(?P<type>[A-Za-z_-]+)\b", line)
            if task_type and task_type.group("type").lower() in {"home", "recents", "dream", "assistant"}:
                item["excluded"] = True

            # Samsung/AOSP task summaries often carry the affinity package as
            # ``A=<uid>:package`` before the ActivityRecord lines.
            affinity = re.search(r"\bA=(?:\d+:)?(?P<pkg>[A-Za-z][A-Za-z0-9_.]+)\b", line)
            if affinity and _PACKAGE_RE.fullmatch(affinity.group("pkg")):
                item.setdefault("package_name", affinity.group("pkg"))

        component_match = _COMPONENT_RE.search(line)
        if not component_match:
            continue

        record_task = task_id if task_id is not None else current_task
        if record_task is None:
            continue
        package_name = component_match.group("package")
        component_name = component_match.group(0)
        if not _PACKAGE_RE.fullmatch(package_name):
            continue

        item = tasks.setdefault(record_task, {})
        item["package_name"] = package_name
        item["component_name"] = component_name
        item.setdefault("display_id", current_display)
        if explicit_display is not None:
            item["display_id"] = explicit_display
        visible = _VISIBLE_RE.search(line)
        if visible:
            item["visible"] = visible.group("value").lower() == "true"
        if "ResumedActivity" in line or "topResumedActivity" in line or "mResumedActivity" in line:
            item["resumed"] = True
            item["visible"] = True

    values: list[RunningGuiApp] = []
    for task_id, item in tasks.items():
        component_name = item.get("component_name")
        package_name = item.get("package_name")
        if not isinstance(component_name, str) or not isinstance(package_name, str):
            continue
        if item.get("excluded") or package_name in {"com.android.systemui", "com.google.android.systemui"}:
            continue
        values.append(
            RunningGuiApp(
                task_id=task_id,
                package_name=package_name,
                component_name=component_name,
                display_id=item.get("display_id") if isinstance(item.get("display_id"), int) else None,
                visible=bool(item.get("visible", False)),
                resumed=bool(item.get("resumed", False)),
                label=(
                    normalize_app_label(application_labels[package_name], package_name)
                    if application_labels and package_name in application_labels
                    else fallback_app_label(package_name)
                ),
            )
        )

    return sorted(values, key=lambda value: (not value.resumed, not value.visible, value.label.lower(), value.task_id))
