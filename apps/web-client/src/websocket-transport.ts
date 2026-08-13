import type { BridgeTransport } from "@droid-web-display/scrcpy-protocol";
import { controlDebug } from "./control-debug.js";

export type WebSocketFactory = (url: string) => WebSocket;

type LatencyMetrics = Record<string, number | string | boolean>;

interface QueuedSocketChunk {
  readonly data: Uint8Array;
  readonly receivedAt: number;
}

function latencyMetrics(): LatencyMetrics {
  const root = globalThis as typeof globalThis & { __dwdLatencyMetrics?: LatencyMetrics };
  return root.__dwdLatencyMetrics ??= {};
}

function now(): number {
  return globalThis.performance?.now?.() ?? Date.now();
}

export class WebSocketBridgeTransport implements BridgeTransport {
  readonly #sockets = new Set<WebSocket>();
  readonly #socketChannels = new Map<WebSocket, "video" | "audio" | "control">();
  readonly #clientId = crypto.randomUUID();

  public constructor(
    public readonly sessionId: string,
    private readonly baseUrl = websocketBaseUrl(),
    private readonly socketFactory: WebSocketFactory = (url) => new WebSocket(url),
  ) {}

  public async openVideoChannel(): Promise<ReadableStream<Uint8Array>> {
    return this.openReadableChannel("video");
  }

  public async openAudioChannel(): Promise<ReadableStream<Uint8Array> | null> {
    return this.openReadableChannel("audio");
  }

  public async openControlChannel(): Promise<ReadableWritablePair<Uint8Array, Uint8Array>> {
    const socket = await this.openSocket("control");
    return {
      readable: readableFromSocket(socket, "control"),
      writable: writableToSocket(socket, this.sessionId),
    };
  }

  public diagnostics(): Record<string, unknown> {
    return {
      sessionId: this.sessionId,
      clientId: this.#clientId,
      sockets: [...this.#sockets].map((socket) => ({
        channel: this.#socketChannels.get(socket) ?? "unknown",
        readyState: socket.readyState,
        bufferedAmount: socket.bufferedAmount,
      })),
    };
  }

  public async close(): Promise<void> {
    controlDebug("transport", "close-requested", this.diagnostics());
    for (const socket of this.#sockets) {
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close(1000, "transport closed");
      }
    }
    this.#sockets.clear();
    this.#socketChannels.clear();
    const metrics = latencyMetrics();
    metrics.controlSocketBufferedBytes = 0;
    metrics.videoSocketQueuedBytes = 0;
    metrics.audioSocketQueuedBytes = 0;
    metrics.controlSocketQueuedBytes = 0;
  }

  private async openReadableChannel(channel: "video" | "audio"): Promise<ReadableStream<Uint8Array>> {
    return readableFromSocket(await this.openSocket(channel), channel);
  }

  private async openSocket(channel: "video" | "audio" | "control"): Promise<WebSocket> {
    const url = `${this.baseUrl}/ws/v1/sessions/${encodeURIComponent(this.sessionId)}/${channel}?clientId=${encodeURIComponent(this.#clientId)}`;
    const socket = this.socketFactory(url);
    socket.binaryType = "arraybuffer";
    this.#sockets.add(socket);
    this.#socketChannels.set(socket, channel);
    controlDebug("websocket", "creating", { sessionId: this.sessionId, channel, readyState: socket.readyState });
    try {
      await waitForOpen(socket);
    } catch (error) {
      controlDebug("websocket", "open-failed", { sessionId: this.sessionId, channel, error });
      throw error;
    }
    controlDebug("websocket", "opened", { sessionId: this.sessionId, channel, readyState: socket.readyState });
    socket.addEventListener("error", () => {
      controlDebug("websocket", "error", { sessionId: this.sessionId, channel, readyState: socket.readyState, bufferedAmount: socket.bufferedAmount });
    });
    socket.addEventListener("close", (event) => {
      controlDebug("websocket", "closed", {
        sessionId: this.sessionId,
        channel,
        code: event.code,
        reason: event.reason || "",
        wasClean: event.wasClean,
        bufferedAmount: socket.bufferedAmount,
      });
      this.#sockets.delete(socket);
      this.#socketChannels.delete(socket);
    }, { once: true });
    return socket;
  }
}

function websocketBaseUrl(): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}`;
}

function waitForOpen(socket: WebSocket): Promise<void> {
  return new Promise((resolve, reject) => {
    if (socket.readyState === WebSocket.OPEN) {
      resolve();
      return;
    }
    const cleanup = () => {
      socket.removeEventListener("open", onOpen);
      socket.removeEventListener("error", onError);
      socket.removeEventListener("close", onClose);
    };
    const onOpen = () => {
      cleanup();
      resolve();
    };
    const onError = () => {
      cleanup();
      reject(new Error("WebSocket connection failed"));
    };
    const onClose = (event: CloseEvent) => {
      cleanup();
      reject(new Error(`WebSocket closed before opening (${event.code}: ${event.reason})`));
    };
    socket.addEventListener("open", onOpen, { once: true });
    socket.addEventListener("error", onError, { once: true });
    socket.addEventListener("close", onClose, { once: true });
  });
}

function maximumIncomingQueueBytes(channel: "video" | "audio" | "control"): number {
  // WebSocket itself has no receive-side backpressure API. Keep only a small,
  // explicit queue between WebSocket delivery and the scrcpy parser. If video
  // exceeds this bound, fail/reconnect rather than displaying increasingly old
  // frames. Chunks cannot be dropped individually because they are byte-stream
  // fragments, not guaranteed H.264 access-unit boundaries.
  if (channel === "video") return 512 * 1024;
  if (channel === "audio") return 256 * 1024;
  return 128 * 1024;
}

function readableFromSocket(socket: WebSocket, channel: "video" | "audio" | "control"): ReadableStream<Uint8Array> {
  const maximumQueuedBytes = maximumIncomingQueueBytes(channel);
  const metricPrefix = `${channel}Socket`;
  let queue: QueuedSocketChunk[] = [];
  let queuedBytes = 0;
  let closed = false;
  let conversionTail: Promise<void> = Promise.resolve();
  let removeListeners = () => undefined;

  return new ReadableStream<Uint8Array>({
    start(controller) {
      const updateQueueMetrics = () => {
        const metrics = latencyMetrics();
        metrics[`${metricPrefix}QueuedBytes`] = queuedBytes;
        metrics[`${metricPrefix}QueuePeakBytes`] = Math.max(
          Number(metrics[`${metricPrefix}QueuePeakBytes`] ?? 0),
          queuedBytes,
        );
      };

      const drain = () => {
        while (!closed && queue.length > 0 && (controller.desiredSize ?? 1) > 0) {
          const item = queue.shift()!;
          queuedBytes = Math.max(0, queuedBytes - item.data.byteLength);
          const metrics = latencyMetrics();
          metrics[`${metricPrefix}QueueDelayMs`] = Math.max(0, now() - item.receivedAt);
          updateQueueMetrics();
          controller.enqueue(item.data);
        }
      };

      const failBacklog = () => {
        if (closed) return;
        closed = true;
        const metrics = latencyMetrics();
        metrics[`${metricPrefix}BacklogOverflows`] = Number(metrics[`${metricPrefix}BacklogOverflows`] ?? 0) + 1;
        metrics[`${metricPrefix}QueuedBytes`] = queuedBytes;
        queue = [];
        queuedBytes = 0;
        removeListeners();
        if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
          socket.close(1013, `${channel} backlog exceeded`);
        }
        controller.error(new Error(`${channel} WebSocket backlog exceeded ${maximumQueuedBytes} bytes; reconnecting instead of rendering stale data`));
      };

      const accept = (data: Uint8Array, receivedAt: number) => {
        if (closed) return;
        const metrics = latencyMetrics();
        metrics[`${metricPrefix}Messages`] = Number(metrics[`${metricPrefix}Messages`] ?? 0) + 1;
        metrics[`${metricPrefix}LastMessageBytes`] = data.byteLength;
        queue.push({ data, receivedAt });
        queuedBytes += data.byteLength;
        updateQueueMetrics();
        if (queuedBytes > maximumQueuedBytes) {
          failBacklog();
          return;
        }
        drain();
      };

      const onMessage = (event: MessageEvent<ArrayBuffer | Blob>) => {
        const receivedAt = now();
        // Serialize Blob conversion with ArrayBuffer delivery so the byte stream
        // cannot be reordered if a browser ignores binaryType for one message.
        conversionTail = conversionTail.then(async () => {
          if (closed) return;
          if (event.data instanceof ArrayBuffer) {
            accept(new Uint8Array(event.data), receivedAt);
            return;
          }
          if (event.data instanceof Blob) {
            accept(new Uint8Array(await event.data.arrayBuffer()), receivedAt);
            return;
          }
          throw new Error("Expected binary WebSocket frame");
        }).catch((error) => {
          if (closed) return;
          closed = true;
          removeListeners();
          controller.error(error);
        });
      };

      const onClose = (event: CloseEvent) => {
        if (closed) return;
        closed = true;
        removeListeners();
        latencyMetrics()[`${metricPrefix}QueuedBytes`] = 0;
        queue = [];
        queuedBytes = 0;
        if (event.code === 1000) controller.close();
        else controller.error(new Error(`WebSocket closed (${event.code}: ${event.reason})`));
      };

      const onError = () => {
        if (closed) return;
        closed = true;
        removeListeners();
        queue = [];
        queuedBytes = 0;
        latencyMetrics()[`${metricPrefix}QueuedBytes`] = 0;
        controller.error(new Error("WebSocket transport error"));
      };

      removeListeners = () => {
        socket.removeEventListener("message", onMessage as EventListener);
        socket.removeEventListener("close", onClose);
        socket.removeEventListener("error", onError);
      };
      socket.addEventListener("message", onMessage as EventListener);
      socket.addEventListener("close", onClose);
      socket.addEventListener("error", onError);
      (controller as ReadableStreamDefaultController<Uint8Array> & { __dwdDrain?: () => void }).__dwdDrain = drain;
    },
    pull(controller) {
      (controller as ReadableStreamDefaultController<Uint8Array> & { __dwdDrain?: () => void }).__dwdDrain?.();
    },
    cancel() {
      closed = true;
      removeListeners();
      queue = [];
      queuedBytes = 0;
      latencyMetrics()[`${metricPrefix}QueuedBytes`] = 0;
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close(1000, "reader cancelled");
      }
    },
  }, { highWaterMark: 1 });
}

function writableToSocket(socket: WebSocket, sessionId: string): WritableStream<Uint8Array> {
  // Control frames are tiny. A megabyte-scale backlog is unacceptable for an
  // interactive pointer/keyboard path, so apply backpressure while the browser
  // has more than 64 KiB queued for the socket.
  const maximumBufferedBytes = 64 * 1024;
  let sampling = false;
  let writeCount = 0;

  const sampleBufferedAmount = () => {
    const metrics = latencyMetrics();
    metrics.controlSocketBufferedBytes = socket.readyState === WebSocket.OPEN ? socket.bufferedAmount : 0;
    if (socket.readyState === WebSocket.OPEN && socket.bufferedAmount > 0) {
      setTimeout(sampleBufferedAmount, 4);
    } else {
      sampling = false;
    }
  };

  const startSampling = () => {
    if (sampling) return;
    sampling = true;
    sampleBufferedAmount();
  };

  return new WritableStream<Uint8Array>({
    async write(chunk) {
      if (socket.readyState !== WebSocket.OPEN) {
        controlDebug("control-writer", "write-rejected", { sessionId, readyState: socket.readyState, bufferedAmount: socket.bufferedAmount });
        throw new Error("Control WebSocket is not open");
      }
      while (socket.bufferedAmount > maximumBufferedBytes) {
        latencyMetrics().controlBackpressureWaits = Number(latencyMetrics().controlBackpressureWaits ?? 0) + 1;
        await new Promise((resolve) => setTimeout(resolve, 1));
        if (socket.readyState !== WebSocket.OPEN) throw new Error("Control WebSocket closed during backpressure wait");
      }
      socket.send(chunk);
      writeCount += 1;
      if (writeCount <= 20 || writeCount % 100 === 0) {
        controlDebug("control-writer", "write", { sessionId, writeCount, bytes: chunk.byteLength, bufferedAmount: socket.bufferedAmount });
      }
      const metrics = latencyMetrics();
      metrics.controlSocketBufferedBytes = socket.bufferedAmount;
      metrics.controlSocketPeakBufferedBytes = Math.max(
        Number(metrics.controlSocketPeakBufferedBytes ?? 0),
        socket.bufferedAmount,
      );
      startSampling();
    },
    close() {
      controlDebug("control-writer", "close", { sessionId, writeCount, readyState: socket.readyState, bufferedAmount: socket.bufferedAmount });
      latencyMetrics().controlSocketBufferedBytes = 0;
      if (socket.readyState === WebSocket.OPEN) socket.close(1000, "control writer closed");
    },
    abort(reason) {
      controlDebug("control-writer", "abort", { sessionId, writeCount, readyState: socket.readyState, reason: String(reason ?? "") });
      latencyMetrics().controlSocketBufferedBytes = 0;
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close(1011, String(reason ?? "control writer aborted"));
      }
    },
  });
}
