from pathlib import Path


def test_optimized_response_time_runtime_contract() -> None:
    root = Path(__file__).resolve().parents[3]
    launcher = (root / "tools/run_bridge_service.py").read_text(encoding="utf-8")
    renderer = (root / "apps/web-client/src/video-renderer.ts").read_text(encoding="utf-8")
    worker = (root / "apps/web-client/src/video-render-worker.ts").read_text(encoding="utf-8")
    transport = (root / "apps/web-client/src/websocket-transport.ts").read_text(encoding="utf-8")
    display = (root / "apps/web-client/src/display-config.ts").read_text(encoding="utf-8")
    protocol = (root / "packages/scrcpy-protocol/src/versions/v4_1/adapter.ts").read_text(encoding="utf-8")
    drawer = (root / "apps/web-client/static/droidwebdisplay-main-drawer.js").read_text(encoding="utf-8")
    dist_drawer = (root / "apps/web-client/dist/droidwebdisplay-main-drawer.js").read_text(encoding="utf-8")

    assert "ws_per_message_deflate=False" in launcher
    assert "DECODER_BACKLOG_RECOVERY_THRESHOLD = 4" in renderer
    assert "STATISTICS_INTERVAL_MS = 250" in renderer
    assert "transferControlToOffscreen" in renderer
    assert "performance.timeOrigin + performance.now()" in worker
    assert "message.presentedAt - performance.timeOrigin" in renderer
    assert "maximumBufferedBytes = 64 * 1024" in transport
    assert "TOUCH_MOVE_INTERVAL_MS = 8" in protocol
    assert "controlMovesCoalesced" in protocol
    assert '"low-latency"' in display
    assert "maxSize: 1600" in display
    assert "maxFps: 60" in display
    assert "latency-hud" in drawer
    assert "/video-encoders/benchmark" in drawer
    assert drawer == dist_drawer
    assert (root / "apps/web-client/dist/assets/video-render-worker.js").is_file()
