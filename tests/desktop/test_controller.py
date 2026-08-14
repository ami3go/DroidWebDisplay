from __future__ import annotations

from pathlib import Path
import threading
import time

from droid_web_display.desktop.controller import DesktopPaths, ServerController, ServerState


class FakeRuntime:
    def __init__(self) -> None:
        self.event = threading.Event()

    @property
    def shutdown_requested(self) -> bool:
        return self.event.is_set()

    def request_shutdown(self) -> None:
        self.event.set()


def _paths(tmp_path: Path) -> DesktopPaths:
    resource = tmp_path / "resource"
    resource.mkdir()
    return DesktopPaths(
        resource_root=resource,
        state_root=tmp_path / "state",
        data_root=tmp_path / "state" / "data",
        downloads_root=tmp_path / "downloads",
        logs_root=tmp_path / "state" / "logs",
        adb_executable="adb",
    )


def test_controller_starts_and_stops_managed_server(tmp_path: Path, monkeypatch) -> None:
    runtime_holder: list[FakeRuntime] = []

    def runtime_factory() -> FakeRuntime:
        runtime = FakeRuntime()
        runtime_holder.append(runtime)
        return runtime

    def runner(argv, runtime) -> int:
        assert "--repo-root" in argv
        assert "--no-browser" in argv
        assert runtime is runtime_holder[-1]
        while not runtime.shutdown_requested:
            time.sleep(0.01)
        return 0

    controller = ServerController(
        _paths(tmp_path),
        server_runner=runner,
        runtime_factory=runtime_factory,
        server_args=["--port", "9876"],
    )
    monkeypatch.setattr(controller, "_probe", lambda _url: False)

    assert controller.start() is True
    assert controller.start() is False
    assert controller.snapshot(include_device=False).state == ServerState.STARTING
    assert controller.stop(timeout=2.0) is True
    assert controller.snapshot(include_device=False).state == ServerState.STOPPED
    assert runtime_holder[-1].shutdown_requested is True


def test_snapshot_recognizes_existing_external_server(tmp_path: Path, monkeypatch) -> None:
    controller = ServerController(
        _paths(tmp_path),
        server_runner=lambda _argv, _runtime: 0,
        runtime_factory=FakeRuntime,
    )
    monkeypatch.setattr(controller, "_probe", lambda _url: True)

    snapshot = controller.snapshot(include_device=False)

    assert snapshot.state == ServerState.EXTERNAL
    assert snapshot.url == "http://127.0.0.1:8765/"


def test_server_arguments_use_persistent_desktop_paths(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    arguments = paths.server_arguments(["--port", "9000"])

    assert arguments[arguments.index("--repo-root") + 1] == str(paths.resource_root)
    assert arguments[arguments.index("--data-directory") + 1] == str(paths.data_root)
    assert arguments[arguments.index("--download-directory") + 1] == str(paths.downloads_root)
    assert arguments[-2:] == ["--port", "9000"]
