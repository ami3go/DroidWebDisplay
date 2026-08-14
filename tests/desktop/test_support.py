from __future__ import annotations

import json
from pathlib import Path
import zipfile

from droid_web_display.desktop.controller import DesktopPaths, ServerSnapshot, ServerState
from droid_web_display.desktop.support import (
    diagnostic_summary,
    export_diagnostics_bundle,
    read_log_entries,
)


def _paths(tmp_path: Path) -> DesktopPaths:
    logs = tmp_path / "logs"
    data = tmp_path / "data"
    downloads = tmp_path / "downloads"
    for path in (logs, data, downloads):
        path.mkdir(parents=True, exist_ok=True)
    return DesktopPaths(
        resource_root=tmp_path,
        state_root=tmp_path,
        data_root=data,
        downloads_root=downloads,
        logs_root=logs,
        adb_executable=tmp_path / "missing-adb",
    )


def _snapshot() -> ServerSnapshot:
    return ServerSnapshot(
        state=ServerState.RUNNING,
        url="http://127.0.0.1:8765/",
        network_mode="local-only",
        pid=1234,
        uptime_seconds=45,
        device="SM-G980F",
        last_error="None",
    )


def test_log_reader_filters_server_jsonl_by_level_and_search(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    records = [
        {
            "timestamp": "2026-08-14T18:00:00.000Z",
            "level": "INFO",
            "message": "Server started",
            "event": "server.started",
        },
        {
            "timestamp": "2026-08-14T18:00:01.000Z",
            "level": "ERROR",
            "message": "scrcpy connection failed",
            "event": "websocket.exception",
        },
    ]
    (paths.logs_root / "server.log").write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    entries = read_log_entries(
        paths.logs_root,
        source="Server",
        minimum_level="ERROR",
        search="scrcpy",
    )

    assert len(entries) == 1
    assert entries[0].level == "ERROR"
    assert "scrcpy connection failed" in entries[0].display_line()


def test_export_diagnostics_bundle_redacts_secrets_and_includes_rotated_logs(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    (paths.logs_root / "server.log").write_text(
        '{"level":"ERROR","message":"token=secret-value pin=1234"}\n',
        encoding="utf-8",
    )
    (paths.logs_root / "server.log.1").write_text(
        "Authorization: Bearer abcdef\n",
        encoding="utf-8",
    )
    (paths.logs_root / "desktop-host.log").write_text(
        "csrf=hidden-value\n",
        encoding="utf-8",
    )

    bundle = export_diagnostics_bundle(paths, _snapshot())

    assert bundle.is_file()
    with zipfile.ZipFile(bundle) as archive:
        names = set(archive.namelist())
        assert "diagnostics.json" in names
        assert "diagnostic-summary.txt" in names
        assert "logs/server.log" in names
        assert "logs/server.log.1" in names
        assert "logs/desktop-host.log" in names
        combined = "\n".join(
            archive.read(name).decode("utf-8", errors="replace")
            for name in names
            if name.endswith(".log") or ".log." in name
        )
    assert "secret-value" not in combined
    assert "1234" not in combined
    assert "abcdef" not in combined
    assert "hidden-value" not in combined
    assert "[REDACTED]" in combined


def test_diagnostic_summary_contains_runtime_identity_without_secrets(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    text = diagnostic_summary(paths, _snapshot())
    assert "DroidWebDisplay:" in text
    assert "Server state: running" in text
    assert "Android device: SM-G980F" in text
    assert "Logs:" in text
