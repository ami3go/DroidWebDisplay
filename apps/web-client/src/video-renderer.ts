import {
  extractH264DecoderConfiguration,
  type MediaPacket,
  type ScrcpyV41Session,
  type VideoSessionMeta,
} from "@droid-web-display/scrcpy-protocol";

const DECODER_BACKLOG_RECOVERY_THRESHOLD = 4;
const STATISTICS_INTERVAL_MS = 250;

export interface VideoStatistics {
  readonly framesDecoded: number;
  readonly framesPresented: number;
  readonly framesDropped: number;
  readonly width: number;
  readonly height: number;
  readonly decoderQueue: number;
  readonly lastPts: number;
  readonly sessionChanges: number;
  readonly fps: number;
  readonly decodeLatencyMs: number;
  readonly presentationLatencyMs: number;
  readonly browserPipelineMs: number;
  readonly decoderRecoveries: number;
  readonly rendererBackend: "offscreen-worker" | "canvas2d";
}

export type StatisticsListener = (statistics: VideoStatistics) => void;

interface ResizeWaiter {
  readonly previousWidth: number;
  readonly previousHeight: number;
  readonly resolve: (size: { width: number; height: number }) => void;
  readonly reject: (error: Error) => void;
  readonly timer: number;
}

interface RenderWorkerMessage {
  readonly type: "ready" | "presented";
  readonly timestamp?: number;
  readonly presentedAt?: number;
  readonly drawMilliseconds?: number;
  readonly dropped?: number;
}

type LatencyMetrics = Record<string, number | string | boolean>;

function latencyMetrics(): LatencyMetrics {
  const root = globalThis as typeof globalThis & { __dwdLatencyMetrics?: LatencyMetrics };
  return root.__dwdLatencyMetrics ??= {};
}

function now(): number {
  return performance.now();
}

export class WebCodecsVideoRenderer {
  #decoder: VideoDecoder | null = null;
  #decoderConfig: VideoDecoderConfig | null = null;
  #configurationPacket: Uint8Array | null = null;
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
  #context: CanvasRenderingContext2D | null = null;
  #worker: Worker | null = null;
  #rendererBackend: "offscreen-worker" | "canvas2d" = "canvas2d";
  #pendingFrame: VideoFrame | null = null;
  #animationFrame: number | null = null;
  readonly #packetArrivals = new Map<number, number>();
  readonly #decodeOutputs = new Map<number, number>();
  readonly #resizeWaiters = new Set<ResizeWaiter>();

  public constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly onStatistics: StatisticsListener = () => undefined,
  ) {
    this.initializeRenderingBackend();
  }

  public get screenSize(): { width: number; height: number } {
    return { width: this.#width, height: this.#height };
  }

  public async run(session: ScrcpyV41Session): Promise<void> {
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

  public stop(): void {
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

  public waitForScreenSizeChange(
    previous: { width: number; height: number },
    timeoutMs = 8_000,
  ): Promise<{ width: number; height: number }> {
    if (this.#width !== previous.width || this.#height !== previous.height) {
      return Promise.resolve(this.screenSize);
    }
    return new Promise((resolve, reject) => {
      const waiter: ResizeWaiter = {
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

  private initializeRenderingBackend(): void {
    const metrics = latencyMetrics();
    const offscreenCapable = typeof Worker !== "undefined" && "transferControlToOffscreen" in this.canvas;
    if (offscreenCapable) {
      try {
        const worker = new Worker(new URL("./video-render-worker.js", import.meta.url), { type: "module" });
        const offscreen = this.canvas.transferControlToOffscreen();
        worker.addEventListener("message", (event: MessageEvent<RenderWorkerMessage>) => this.onWorkerMessage(event.data));
        worker.addEventListener("error", (event) => {
          metrics.videoWorkerError = event.message || "OffscreenCanvas worker failed";
        });
        worker.postMessage({ type: "init", canvas: offscreen }, [offscreen]);
        this.#worker = worker;
        this.#rendererBackend = "offscreen-worker";
        metrics.rendererBackend = this.#rendererBackend;
        return;
      } catch (error) {
        metrics.videoWorkerError = error instanceof Error ? error.message : String(error);
      }
    }

    this.#context = this.canvas.getContext("2d", { alpha: false, desynchronized: true });
    if (!this.#context) throw new Error("Canvas 2D context is unavailable");
    this.#rendererBackend = "canvas2d";
    metrics.rendererBackend = this.#rendererBackend;
  }

  private async processPacket(packet: MediaPacket): Promise<void> {
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

    if (packet.keyFrame) this.#awaitingKeyFrame = false;
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

  private applySession(session: VideoSessionMeta, restarted: boolean): void {
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

  private async configure(data: Uint8Array): Promise<void> {
    const h264 = extractH264DecoderConfiguration(data);
    const config: VideoDecoderConfig = {
      codec: h264.codec,
      optimizeForLatency: true,
      hardwareAcceleration: "prefer-hardware",
    };
    const support = await VideoDecoder.isConfigSupported(config);
    if (!support.supported) throw new Error(`Browser cannot decode ${h264.codec}`);

    this.#configurationPacket = data.slice();
    this.closeDecoder();
    this.#decoderConfig = support.config ?? config;
    this.createConfiguredDecoder();
  }

  private createConfiguredDecoder(): void {
    if (!this.#decoderConfig) throw new Error("Video decoder configuration is unavailable");
    this.#decoder = new VideoDecoder({
      output: (frame) => this.queueDecodedFrame(frame),
      error: (error) => {
        latencyMetrics().videoDecoderError = error.message;
        console.error("VideoDecoder error", error);
      },
    });
    this.#decoder.configure(this.#decoderConfig);
  }

  private recoverDecoderBacklog(): void {
    if (!this.#decoder || !this.#decoderConfig || this.#decoder.state === "closed") return;
    this.#decoder.reset();
    this.#decoder.configure(this.#decoderConfig);
    this.#decoderRecoveries += 1;
    this.#awaitingKeyFrame = true;
    this.#packetArrivals.clear();
    this.#decodeOutputs.clear();
    latencyMetrics().decoderRecoveries = this.#decoderRecoveries;
  }

  private closeDecoder(): void {
    if (this.#decoder && this.#decoder.state !== "closed") this.#decoder.close();
    this.#decoder = null;
    this.#awaitingKeyFrame = false;
    this.#packetArrivals.clear();
    this.#decodeOutputs.clear();
  }

  private queueDecodedFrame(frame: VideoFrame): void {
    const decodedAt = now();
    const timestamp = frame.timestamp;
    const arrivedAt = this.#packetArrivals.get(timestamp);
    if (arrivedAt !== undefined) this.#decodeLatencyMs = Math.max(0, decodedAt - arrivedAt);
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
    } else {
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

  private presentLatestFrame(): void {
    this.#animationFrame = null;
    const frame = this.#pendingFrame;
    this.#pendingFrame = null;
    if (!frame || !this.#context) return;
    try {
      this.#context.drawImage(frame, 0, 0, this.canvas.width, this.canvas.height);
      this.recordPresentation(frame.timestamp, now(), 0);
    } finally {
      frame.close();
    }
    if (this.#pendingFrame && this.#animationFrame === null) {
      this.#animationFrame = window.requestAnimationFrame(() => this.presentLatestFrame());
    }
  }

  private onWorkerMessage(message: RenderWorkerMessage): void {
    if (message.type === "ready") {
      latencyMetrics().rendererBackend = "offscreen-worker";
      return;
    }
    if (message.type !== "presented" || message.timestamp === undefined || message.presentedAt === undefined) return;
    if (message.dropped) this.#framesDropped += message.dropped;
    this.recordPresentation(message.timestamp, message.presentedAt, message.drawMilliseconds ?? 0);
  }

  private recordPresentation(timestamp: number, presentedAt: number, drawMilliseconds: number): void {
    const decodedAt = this.#decodeOutputs.get(timestamp);
    const arrivedAt = this.#packetArrivals.get(timestamp);
    if (decodedAt !== undefined) this.#presentationLatencyMs = Math.max(0, presentedAt - decodedAt);
    if (arrivedAt !== undefined) this.#browserPipelineMs = Math.max(0, presentedAt - arrivedAt);
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

  private clearPendingFrame(): void {
    if (this.#animationFrame !== null) {
      window.cancelAnimationFrame(this.#animationFrame);
      this.#animationFrame = null;
    }
    this.#pendingFrame?.close();
    this.#pendingFrame = null;
  }

  private resizeCanvas(width: number, height: number): void {
    if (this.#worker) {
      this.#worker.postMessage({ type: "resize", width, height });
    } else {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    this.canvas.style.aspectRatio = `${width} / ${height}`;
  }

  private resolveResizeWaiters(): void {
    for (const waiter of [...this.#resizeWaiters]) {
      if (this.#width === waiter.previousWidth && this.#height === waiter.previousHeight) continue;
      window.clearTimeout(waiter.timer);
      this.#resizeWaiters.delete(waiter);
      waiter.resolve(this.screenSize);
    }
  }

  private emitStatistics(force = false): void {
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
    if (!force && timestamp - this.#lastStatisticsAt < STATISTICS_INTERVAL_MS) return;
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

  private trimTimingMaps(): void {
    while (this.#packetArrivals.size > 256) {
      const first = this.#packetArrivals.keys().next().value;
      if (first === undefined) break;
      this.#packetArrivals.delete(first);
    }
    while (this.#decodeOutputs.size > 256) {
      const first = this.#decodeOutputs.keys().next().value;
      if (first === undefined) break;
      this.#decodeOutputs.delete(first);
    }
  }
}

function concatenate(first: Uint8Array, second: Uint8Array): Uint8Array {
  const result = new Uint8Array(first.byteLength + second.byteLength);
  result.set(first, 0);
  result.set(second, first.byteLength);
  return result;
}
