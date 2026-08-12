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
    latency_api = (root / "droid_web_display/api/latency.py").read_text(encoding="utf-8")
    tuning = (root / "droid_web_display/scrcpy/encoder_tuning.py").read_text(encoding="utf-8")
    hardening = (root / "droid_web_display/runtime_hardening.py").read_text(encoding="utf-8")

    assert "ws_per_message_deflate=False" in launcher

    # Receive-side latency is explicitly bounded because browser WebSocket has
    # no native receive backpressure and arbitrary H.264 byte fragments cannot
    # safely be dropped one by one.
    assert 'if (channel === "video") return 512 * 1024' in transport
    assert "video WebSocket backlog exceeded" not in transport  # message is channel-generic
    assert "BacklogOverflows" in transport
    assert "QueueDelayMs" in transport
    assert "maximumBufferedBytes = 64 * 1024" in transport

    # Decoder recovery must keep an arriving keyframe after reset.
    assert "DECODER_BACKLOG_RECOVERY_THRESHOLD = 4" in renderer
    assert "if (this.#decoder.decodeQueueSize >= DECODER_BACKLOG_RECOVERY_THRESHOLD)" in renderer
    assert "if (!packet.keyFrame)" in renderer
    assert "this.#awaitingKeyFrame = false" in renderer
    assert "parserToDrawMs" in renderer
    assert "MAX_RENDER_WORKER_RESTARTS" in renderer
    assert 'message.type === "fatal"' in renderer
    assert "performance.timeOrigin + performance.now()" in worker
    assert 'type: "fatal"' in worker

    # MOVE traffic is latest-wins per pointer, not globally latest-wins.
    assert "TOUCH_MOVE_INTERVAL_MS = 8" in protocol
    assert "#pendingMoves = new Map<bigint, PendingMove>()" in protocol
    assert "message.pointerId" in protocol
    assert "controlMovesCoalesced" in protocol

    # Encoder diagnostics are explicit/cached and compatibility-only. Startup
    # timing must never silently become an automatic latency recommendation.
    assert "probe: bool = False" in latency_api
    assert '"automaticSelection": "scrcpy"' in latency_api
    assert '"benchmarkKind": "startup-compatibility"' in latency_api
    assert "return self.preference(serial)" in tuning
    assert "preferred-encoder-start-failed" in hardening

    assert '"low-latency"' in display
    assert "maxSize: 1600" in display
    assert "maxFps: 60" in display
    assert "latency-hud" in drawer
    assert "parser→draw" in drawer
    assert "WS queue" in drawer
    assert "Compatibility test" in drawer
    assert drawer == dist_drawer
    assert (root / "apps/web-client/dist/assets/video-render-worker.js").is_file()
