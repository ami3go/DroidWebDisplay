from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from run_bridge_service import BridgeServiceRuntime  # noqa: E402


class FakeServer:
    def __init__(self) -> None:
        self.should_exit = False


def test_runtime_requests_clean_uvicorn_shutdown() -> None:
    runtime = BridgeServiceRuntime()
    server = FakeServer()

    runtime.attach(server)
    runtime.request_shutdown()

    assert runtime.shutdown_requested is True
    assert server.should_exit is True


def test_runtime_applies_prior_shutdown_when_server_attaches() -> None:
    runtime = BridgeServiceRuntime()
    runtime.request_shutdown()
    server = FakeServer()

    runtime.attach(server)

    assert server.should_exit is True
