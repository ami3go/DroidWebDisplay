import { extractH264DecoderConfiguration, } from "@droid-web-display/scrcpy-protocol";
const DECODER_BACKLOG_RECOVERY_THRESHOLD = 4;
const STATISTICS_INTERVAL_MS = 250;
function latencyMetrics() {
    const root = globalThis;
    return root.__dwdLatencyMetrics ??= {};
}
function now() {
    return performance.now();
}
export class WebCodecsVideoRenderer {
    canvas;
    onStatistics;
    #decoder = null;
    #decoderConfig = null;
    #configurationPacket = null;
    #stopped = false;
    #framesDecoded = 0;
    #framesPresented = 0;
    #framesDropped = 0;
    #width = 0;
    #height = 0;
    #lastPts = 0;
    #lastTimestamp = 0;
    #sessionChanges = 0;
    #decoderRecoveries = 0;
    #awaitingKeyFrame = false;
    #decodeLatencyMs = 0;
    #presentationLatencyMs = 0;
    #browserPipelineMs = 0;
    #fps = 0;
    #fpsWindowStartedAt = now();
    #fpsWindowFrames = 0;
    #lastStatisticsAt = 0;
    #context = null;
    #worker = null;
    #rendererBackend = "canvas2d";
    #pendingFrame = null;
    #animationFrame = null;
    #packetArrivals = new Map();
    #decodeOutputs = new Map();
    #resizeWaiters = new Set();
    constructor(canvas, onStatistics = () => undefined) {
        this.canvas = canvas;
        this.onStatistics = onStatistics;
        this.initializeRenderingBackend();
    }
    get screenSize() {
        return { width: this.#width, height: this.#height };
    }
    async run(session) {
        const header = session.videoHeader;
        if (!header || header.codec !== "h264" || !header.session) {
            throw new Error("An H.264 video session header is required");
        }
        this.applySession(header.session, false);
        this.#stopped = false;
        while (!this.#stopped) {
            const packet = await session.readVideoPacket();
            await this.processPacket(packet);
        }
    }
    stop() {
        this.#stopped = true;
        this.closeDecoder();
        this.clearPendingFrame();
        this.#worker?.postMessage({ type: "clear" });
        for (const waiter of this.#resizeWaiters) {
            window.clearTimeout(waiter.timer);
            waiter.reject(new Error("Video renderer stopped before rotation completed"));
        }
        this.#resizeWaiters.clear();
    }
    waitForScreenSizeChange(previous, timeoutMs = 8_000) {
        if (this.#width !== previous.width || this.#height !== previous.height) {
            return Promise.resolve(this.screenSize);
        }
        return new Promise((resolve, reject) => {
            const waiter = {
                previousWidth: previous.width,
                previousHeight: previous.height,
                resolve,
                reject,
                timer: window.setTimeout(() => {
                    this.#resizeWaiters.delete(waiter);
                    reject(new Error("Timed out waiting for rotated video dimensions"));
                }, timeoutMs),
            };
            this.#resizeWaiters.add(waiter);
        });
    }
    initializeRenderingBackend() {
        const metrics = latencyMetrics();
        const offscreenCapable = typeof Worker !== "undefined" && "transferControlToOffscreen" in this.canvas;
        if (offscreenCapable) {
            try {
                const worker = new Worker(new URL("./video-render-worker.js", import.meta.url), { type: "module" });
                const offscreen = this.canvas.transferControlToOffscreen();
                worker.addEventListener("message", (event) => this.onWorkerMessage(event.data));
                worker.addEventListener("error", (event) => {
                    metrics.videoWorkerError = event.message || "OffscreenCanvas worker failed";
                });
                worker.postMessage({ type: "init", canvas: offscreen }, [offscreen]);
                this.#worker = worker;
                this.#rendererBackend = "offscreen-worker";
                metrics.rendererBackend = this.#rendererBackend;
                return;
            }
            catch (error) {
                metrics.videoWorkerError = error instanceof Error ? error.message : String(error);
            }
        }
        this.#context = this.canvas.getContext("2d", { alpha: false, desynchronized: true });
        if (!this.#context)
            throw new Error("Canvas 2D context is unavailable");
        this.#rendererBackend = "canvas2d";
        metrics.rendererBackend = this.#rendererBackend;
    }
    async processPacket(packet) {
        if (packet.session) {
            this.applySession(packet.session, true);
            return;
        }
        if (packet.configuration) {
            await this.configure(packet.data);
            return;
        }
        if (!this.#decoder || this.#decoder.state !== "configured") {
            throw new Error("Received video frame before H.264 decoder configuration");
        }
        if (this.#awaitingKeyFrame && !packet.keyFrame) {
            this.#framesDropped += 1;
            this.emitStatistics();
            return;
        }
        if (this.#decoder.decodeQueueSize >= DECODER_BACKLOG_RECOVERY_THRESHOLD && !packet.keyFrame) {
            this.recoverDecoderBacklog();
            this.#framesDropped += 1;
            this.emitStatistics(true);
            return;
        }
        if (packet.keyFrame)
            this.#awaitingKeyFrame = false;
        const pts = packet.pts === null ? this.#lastTimestamp + 33_333 : Number(packet.pts);
        this.#lastTimestamp = Math.max(pts, this.#lastTimestamp + 1);
        this.#lastPts = this.#lastTimestamp;
        const data = packet.keyFrame && this.#configurationPacket
            ? concatenate(this.#configurationPacket, packet.data)
            : packet.data;
        this.#packetArrivals.set(this.#lastTimestamp, now());
        this.trimTimingMaps();
        this.#decoder.decode(new EncodedVideoChunk({
            type: packet.keyFrame ? "key" : "delta",
            timestamp: this.#lastTimestamp,
            data,
        }));
        this.emitStatistics();
    }
    applySession(session, restarted) {
        this.#width = session.width;
        this.#height = session.height;
        this.resizeCanvas(this.#width, this.#height);
        if (restarted) {
            this.#sessionChanges += 1;
            this.#configurationPacket = null;
            this.#decoderConfig = null;
            this.closeDecoder();
        }
        this.resolveResizeWaiters();
        this.emitStatistics(true);
    }
    async configure(data) {
        const h264 = extractH264DecoderConfiguration(data);
        const config = {
            codec: h264.codec,
            optimizeForLatency: true,
            hardwareAcceleration: "prefer-hardware",
        };
        const support = await VideoDecoder.isConfigSupported(config);
        if (!support.supported)
            throw new Error(`Browser cannot decode ${h264.codec}`);
        this.#configurationPacket = data.slice();
        this.closeDecoder();
        this.#decoderConfig = support.config ?? config;
        this.createConfiguredDecoder();
    }
    createConfiguredDecoder() {
        if (!this.#decoderConfig)
            throw new Error("Video decoder configuration is unavailable");
        this.#decoder = new VideoDecoder({
            output: (frame) => this.queueDecodedFrame(frame),
            error: (error) => {
                latencyMetrics().videoDecoderError = error.message;
                console.error("VideoDecoder error", error);
            },
        });
        this.#decoder.configure(this.#decoderConfig);
    }
    recoverDecoderBacklog() {
        if (!this.#decoder || !this.#decoderConfig || this.#decoder.state === "closed")
            return;
        this.#decoder.reset();
        this.#decoder.configure(this.#decoderConfig);
        this.#decoderRecoveries += 1;
        this.#awaitingKeyFrame = true;
        this.#packetArrivals.clear();
        this.#decodeOutputs.clear();
        latencyMetrics().decoderRecoveries = this.#decoderRecoveries;
    }
    closeDecoder() {
        if (this.#decoder && this.#decoder.state !== "closed")
            this.#decoder.close();
        this.#decoder = null;
        this.#awaitingKeyFrame = false;
        this.#packetArrivals.clear();
        this.#decodeOutputs.clear();
    }
    queueDecodedFrame(frame) {
        const decodedAt = now();
        const timestamp = frame.timestamp;
        const arrivedAt = this.#packetArrivals.get(timestamp);
        if (arrivedAt !== undefined)
            this.#decodeLatencyMs = Math.max(0, decodedAt - arrivedAt);
        this.#decodeOutputs.set(timestamp, decodedAt);
        this.#framesDecoded += 1;
        const width = frame.displayWidth || frame.codedWidth;
        const height = frame.displayHeight || frame.codedHeight;
        if (width !== this.#width || height !== this.#height) {
            this.#width = width;
            this.#height = height;
            this.resizeCanvas(width, height);
            this.resolveResizeWaiters();
        }
        if (this.#worker) {
            this.#worker.postMessage({ type: "frame", frame }, [frame]);
        }
        else {
            if (this.#pendingFrame) {
                this.#pendingFrame.close();
                this.#pendingFrame = null;
                this.#framesDropped += 1;
            }
            this.#pendingFrame = frame;
            if (this.#animationFrame === null) {
                this.#animationFrame = window.requestAnimationFrame(() => this.presentLatestFrame());
            }
        }
        this.emitStatistics();
    }
    presentLatestFrame() {
        this.#animationFrame = null;
        const frame = this.#pendingFrame;
        this.#pendingFrame = null;
        if (!frame || !this.#context)
            return;
        try {
            this.#context.drawImage(frame, 0, 0, this.canvas.width, this.canvas.height);
            this.recordPresentation(frame.timestamp, now(), 0);
        }
        finally {
            frame.close();
        }
        if (this.#pendingFrame && this.#animationFrame === null) {
            this.#animationFrame = window.requestAnimationFrame(() => this.presentLatestFrame());
        }
    }
    onWorkerMessage(message) {
        if (message.type === "ready") {
            latencyMetrics().rendererBackend = "offscreen-worker";
            return;
        }
        if (message.type !== "presented" || message.timestamp === undefined || message.presentedAt === undefined)
            return;
        if (message.dropped)
            this.#framesDropped += message.dropped;
        this.recordPresentation(message.timestamp, message.presentedAt - performance.timeOrigin, message.drawMilliseconds ?? 0);
    }
    recordPresentation(timestamp, presentedAt, drawMilliseconds) {
        const decodedAt = this.#decodeOutputs.get(timestamp);
        const arrivedAt = this.#packetArrivals.get(timestamp);
        if (decodedAt !== undefined)
            this.#presentationLatencyMs = Math.max(0, presentedAt - decodedAt);
        if (arrivedAt !== undefined)
            this.#browserPipelineMs = Math.max(0, presentedAt - arrivedAt);
        this.#decodeOutputs.delete(timestamp);
        this.#packetArrivals.delete(timestamp);
        this.#framesPresented += 1;
        this.#fpsWindowFrames += 1;
        const elapsed = presentedAt - this.#fpsWindowStartedAt;
        if (elapsed >= 500) {
            this.#fps = this.#fpsWindowFrames * 1000 / elapsed;
            this.#fpsWindowFrames = 0;
            this.#fpsWindowStartedAt = presentedAt;
        }
        const metrics = latencyMetrics();
        metrics.videoDrawMs = drawMilliseconds;
        this.emitStatistics();
    }
    clearPendingFrame() {
        if (this.#animationFrame !== null) {
            window.cancelAnimationFrame(this.#animationFrame);
            this.#animationFrame = null;
        }
        this.#pendingFrame?.close();
        this.#pendingFrame = null;
    }
    resizeCanvas(width, height) {
        if (this.#worker) {
            this.#worker.postMessage({ type: "resize", width, height });
        }
        else {
            this.canvas.width = width;
            this.canvas.height = height;
        }
        this.canvas.style.aspectRatio = `${width} / ${height}`;
    }
    resolveResizeWaiters() {
        for (const waiter of [...this.#resizeWaiters]) {
            if (this.#width === waiter.previousWidth && this.#height === waiter.previousHeight)
                continue;
            window.clearTimeout(waiter.timer);
            this.#resizeWaiters.delete(waiter);
            waiter.resolve(this.screenSize);
        }
    }
    emitStatistics(force = false) {
        const timestamp = now();
        const decoderQueue = this.#decoder?.decodeQueueSize ?? 0;
        const current = latencyMetrics();
        current.videoFps = Number(this.#fps.toFixed(1));
        current.decoderQueue = decoderQueue;
        current.decodeLatencyMs = Number(this.#decodeLatencyMs.toFixed(1));
        current.presentationLatencyMs = Number(this.#presentationLatencyMs.toFixed(1));
        current.browserPipelineMs = Number(this.#browserPipelineMs.toFixed(1));
        current.videoFramesDecoded = this.#framesDecoded;
        current.videoFramesPresented = this.#framesPresented;
        current.videoFramesDropped = this.#framesDropped;
        current.decoderRecoveries = this.#decoderRecoveries;
        current.rendererBackend = this.#rendererBackend;
        if (!force && timestamp - this.#lastStatisticsAt < STATISTICS_INTERVAL_MS)
            return;
        this.#lastStatisticsAt = timestamp;
        this.onStatistics({
            framesDecoded: this.#framesDecoded,
            framesPresented: this.#framesPresented,
            framesDropped: this.#framesDropped,
            width: this.#width,
            height: this.#height,
            decoderQueue,
            lastPts: this.#lastPts,
            sessionChanges: this.#sessionChanges,
            fps: this.#fps,
            decodeLatencyMs: this.#decodeLatencyMs,
            presentationLatencyMs: this.#presentationLatencyMs,
            browserPipelineMs: this.#browserPipelineMs,
            decoderRecoveries: this.#decoderRecoveries,
            rendererBackend: this.#rendererBackend,
        });
    }
    trimTimingMaps() {
        while (this.#packetArrivals.size > 256) {
            const first = this.#packetArrivals.keys().next().value;
            if (first === undefined)
                break;
            this.#packetArrivals.delete(first);
        }
        while (this.#decodeOutputs.size > 256) {
            const first = this.#decodeOutputs.keys().next().value;
            if (first === undefined)
                break;
            this.#decodeOutputs.delete(first);
        }
    }
}
function concatenate(first, second) {
    const result = new Uint8Array(first.byteLength + second.byteLength);
    result.set(first, 0);
    result.set(second, first.byteLength);
    return result;
}
//# sourceMappingURL=video-renderer.js.map