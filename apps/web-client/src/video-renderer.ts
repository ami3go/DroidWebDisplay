import {
  extractH264DecoderConfiguration,
  type MediaPacket,
  type ScrcpyV41Session,
  type VideoSessionMeta,
} from "@droid-web-display/scrcpy-protocol";

const DECODER_BACKLOG_RECOVERY_THRESHOLD = 8;

export type DecoderBacklogAction = "decode" | "recover-at-keyframe";

export function decoderBacklogAction(queueSize: number, packetIsKeyFrame: boolean): DecoderBacklogAction {
  // H.264 delta frames may depend on earlier delta frames. Dropping one arbitrary
  // delta frame can make following frames undecodable until a future I-frame.
  // Recover only when the current packet is itself a keyframe, which is a safe
  // independent point from which decoding can resume.
  return queueSize > DECODER_BACKLOG_RECOVERY_THRESHOLD && packetIsKeyFrame
    ? "recover-at-keyframe"
    : "decode";
}

export interface VideoStatistics {
  readonly framesDecoded: number;
  readonly framesDropped: number;
  readonly width: number;
  readonly height: number;
  readonly decoderQueue: number;
  readonly lastPts: number;
  readonly sessionChanges: number;
}

export type StatisticsListener = (statistics: VideoStatistics) => void;

interface ResizeWaiter {
  readonly previousWidth: number;
  readonly previousHeight: number;
  readonly resolve: (size: { width: number; height: number }) => void;
  readonly reject: (error: Error) => void;
  readonly timer: number;
}

export class WebCodecsVideoRenderer {
  #decoder: VideoDecoder | null = null;
  #decoderConfig: VideoDecoderConfig | null = null;
  #configurationPacket: Uint8Array | null = null;
  #stopped = false;
  #framesDecoded = 0;
  #framesDropped = 0;
  #width = 0;
  #height = 0;
  #lastPts = 0;
  #lastTimestamp = 0;
  #sessionChanges = 0;
  readonly #resizeWaiters = new Set<ResizeWaiter>();

  public constructor(
    private readonly canvas: HTMLCanvasElement,
    private readonly onStatistics: StatisticsListener = () => undefined,
  ) {}

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
    this.#decoderConfig = null;
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

    if (decoderBacklogAction(this.#decoder.decodeQueueSize, packet.keyFrame) === "recover-at-keyframe") {
      this.recoverDecoderAtKeyFrame();
    }

    const pts = packet.pts === null ? this.#lastTimestamp + 33_333 : Number(packet.pts);
    this.#lastTimestamp = Math.max(pts, this.#lastTimestamp + 1);
    this.#lastPts = this.#lastTimestamp;
    const data = packet.keyFrame && this.#configurationPacket
      ? concatenate(this.#configurationPacket, packet.data)
      : packet.data;
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
    this.emitStatistics();
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
      output: (frame) => this.drawFrame(frame),
      error: (error) => console.error("VideoDecoder error", error),
    });
    this.#decoder.configure(this.#decoderConfig);
  }

  private recoverDecoderAtKeyFrame(): void {
    if (!this.#decoder || !this.#decoderConfig || this.#decoder.state !== "configured") return;
    const discarded = this.#decoder.decodeQueueSize;
    this.#decoder.reset();
    this.#decoder.configure(this.#decoderConfig);
    this.#framesDropped += discarded;
  }

  private closeDecoder(): void {
    if (this.#decoder && this.#decoder.state !== "closed") this.#decoder.close();
    this.#decoder = null;
  }

  private drawFrame(frame: VideoFrame): void {
    try {
      const width = frame.displayWidth || frame.codedWidth;
      const height = frame.displayHeight || frame.codedHeight;
      if (width !== this.#width || height !== this.#height) {
        this.#width = width;
        this.#height = height;
        this.resizeCanvas(width, height);
        this.resolveResizeWaiters();
      }
      const context = this.canvas.getContext("2d", { alpha: false, desynchronized: true });
      if (!context) throw new Error("Canvas 2D context is unavailable");
      context.drawImage(frame, 0, 0, this.canvas.width, this.canvas.height);
      this.#framesDecoded += 1;
      this.emitStatistics();
    } finally {
      frame.close();
    }
  }

  private resizeCanvas(width: number, height: number): void {
    this.canvas.width = width;
    this.canvas.height = height;
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

  private emitStatistics(): void {
    this.onStatistics({
      framesDecoded: this.#framesDecoded,
      framesDropped: this.#framesDropped,
      width: this.#width,
      height: this.#height,
      decoderQueue: this.#decoder?.decodeQueueSize ?? 0,
      lastPts: this.#lastPts,
      sessionChanges: this.#sessionChanges,
    });
  }
}

function concatenate(first: Uint8Array, second: Uint8Array): Uint8Array {
  const result = new Uint8Array(first.byteLength + second.byteLength);
  result.set(first, 0);
  result.set(second, first.byteLength);
  return result;
}
