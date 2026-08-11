from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from .git import ensure_clean, resolve_commit, run_git


AREA_RULES: dict[str, tuple[str, ...]] = {
    "serverCommandLineOptions": (
        "server/src/main/java/com/genymobile/scrcpy/Options.java",
        "server/src/main/java/com/genymobile/scrcpy/Server.java",
        "app/src/options.c",
        "app/src/cli.c",
    ),
    "socketConnectionAndOrder": (
        "DesktopConnection.java",
        "LocalSocket",
        "tunnel",
        "connection.c",
    ),
    "handshakeAndDeviceMetadata": (
        "Device.java",
        "DeviceMessage.java",
        "DesktopConnection.java",
        "device_msg",
        "device.c",
    ),
    "videoPacketAndCodec": (
        "VideoEncoder.java",
        "SurfaceEncoder.java",
        "Streamer.java",
        "video_buffer",
        "codec",
        "video.c",
    ),
    "audioPacketAndCodec": (
        "AudioEncoder.java",
        "AudioCapture.java",
        "Streamer.java",
        "audio_buffer",
        "audio.c",
    ),
    "controlMessages": (
        "ControlMessage.java",
        "Controller.java",
        "control_msg",
        "controller.c",
    ),
    "clipboard": (
        "ClipboardManager.java",
        "clipboard",
        "DeviceMessage.java",
    ),
    "shutdownAndCleanup": (
        "CleanUp.java",
        "Server.java",
        "shutdown",
        "cleanup",
    ),
    "androidApiAndBuild": (
        "build.gradle",
        "settings.gradle",
        "gradle.properties",
        "gradle/wrapper/",
        "AndroidManifest.xml",
        "meson.build",
        "compileSdk",
        "targetSdk",
        "minSdk",
    ),
}

DIFF_TOKEN_RULES: dict[str, tuple[str, ...]] = {
    "serverCommandLineOptions": ("new_display", "max_fps", "video_bit_rate", "audio_bit_rate", "Options"),
    "socketConnectionAndOrder": ("videoSocket", "audioSocket", "controlSocket", "dummy byte", "tunnel_forward"),
    "handshakeAndDeviceMetadata": ("deviceName", "codecName", "sendDeviceMeta", "sendCodecMeta"),
    "videoPacketAndCodec": ("packetHeader", "pts", "key frame", "codec config", "videoCodec"),
    "audioPacketAndCodec": ("audioCodec", "AudioCodec", "audioSource", "audioBitRate", "audio_bit_rate", "OPUS", "AAC"),
    "controlMessages": ("TYPE_INJECT", "ControlMessage", "DeviceMessage", "clipboardAck"),
    "clipboard": ("clipboard", "setClipboard", "getClipboard"),
    "shutdownAndCleanup": ("cleanUp", "shutdown", "close()", "release()"),
    "androidApiAndBuild": ("compileSdk", "targetSdk", "minSdk", "com.android.tools.build", "gradle-"),
}


def _parse_name_status(output: str) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    for raw_line in output.splitlines():
        parts = raw_line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1]
        item = {"status": status, "path": path}
        if status.startswith("R") and len(parts) >= 3:
            item["previousPath"] = parts[1]
        changes.append(item)
    return changes


def _match_areas(path: str, diff_text: str) -> list[str]:
    haystack = f"{path}\n{diff_text}".lower()
    matched: list[str] = []
    for area, rules in AREA_RULES.items():
        if any(rule.lower() in path.lower() for rule in rules):
            matched.append(area)
            continue
        if any(token.lower() in haystack for token in DIFF_TOKEN_RULES.get(area, ())):
            matched.append(area)
    return matched


def inspect_protocol_changes(repository: Path, base_revision: str, target_revision: str) -> dict[str, Any]:
    ensure_clean(repository)
    base_commit = resolve_commit(repository, base_revision)
    target_commit = resolve_commit(repository, target_revision)
    name_status = run_git(
        repository,
        ["diff", "--name-status", "--find-renames", f"{base_commit}..{target_commit}"],
    ).stdout
    numstat = run_git(repository, ["diff", "--numstat", f"{base_commit}..{target_commit}"]).stdout
    summary = run_git(repository, ["diff", "--shortstat", f"{base_commit}..{target_commit}"]).stdout.strip()
    changes = _parse_name_status(name_status)
    area_files: dict[str, list[str]] = defaultdict(list)
    file_details: list[dict[str, Any]] = []
    for change in changes:
        path = change["path"]
        diff_text = run_git(
            repository,
            ["diff", "--unified=0", f"{base_commit}..{target_commit}", "--", path],
        ).stdout
        areas = _match_areas(path, diff_text)
        for area in areas:
            area_files[area].append(path)
        file_details.append({**change, "areas": areas})

    insertions = 0
    deletions = 0
    binary_files = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        if parts[0] == "-" or parts[1] == "-":
            binary_files += 1
            continue
        insertions += int(parts[0])
        deletions += int(parts[1])

    critical_areas = {
        "socketConnectionAndOrder",
        "handshakeAndDeviceMetadata",
        "videoPacketAndCodec",
        "audioPacketAndCodec",
        "controlMessages",
    }
    affected = sorted(area_files)
    risk = "high" if critical_areas.intersection(affected) else "medium" if affected else "low"
    unclassified = [item["path"] for item in file_details if not item["areas"]]
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "repository": str(repository.resolve()),
        "baseRevision": base_revision,
        "baseCommit": base_commit,
        "targetRevision": target_revision,
        "targetCommit": target_commit,
        "summary": summary,
        "statistics": {
            "changedFiles": len(changes),
            "insertions": insertions,
            "deletions": deletions,
            "binaryFiles": binary_files,
        },
        "risk": risk,
        "changedAreas": [
            {"area": area, "files": sorted(set(area_files[area]))}
            for area in sorted(area_files)
        ],
        "changedFiles": file_details,
        "unclassifiedFiles": unclassified,
        "reviewRequired": bool(affected),
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# scrcpy Protocol Change Inspection",
        "",
        f"- Base: `{report['baseRevision']}` (`{report['baseCommit']}`)",
        f"- Target: `{report['targetRevision']}` (`{report['targetCommit']}`)",
        f"- Risk: **{str(report['risk']).upper()}**",
        f"- Summary: {report.get('summary') or 'No textual diff summary'}",
        "",
        "## Relevant changed areas",
        "",
    ]
    areas = report.get("changedAreas", [])
    if not areas:
        lines.append("No known protocol-sensitive area was detected. Manual review is still required for an update.")
    else:
        for entry in areas:
            lines.append(f"### {entry['area']}")
            lines.extend(f"- `{path}`" for path in entry["files"])
            lines.append("")
    lines.extend(["## All changed files", ""])
    for item in report.get("changedFiles", []):
        area_text = ", ".join(item.get("areas", [])) or "unclassified"
        lines.append(f"- `{item['status']}` `{item['path']}` — {area_text}")
    lines.extend(
        [
            "",
            "## Required review decision",
            "",
            "Do not promote the adapter to stable until automated protocol evidence, browser evidence, and hardware evidence are recorded.",
            "",
        ]
    )
    return "\n".join(lines)


def write_protocol_report(report: dict[str, Any], output_directory: Path) -> dict[str, str]:
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "protocol-change-report.json"
    md_path = output_directory / "protocol-change-report.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
