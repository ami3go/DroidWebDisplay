import type { BridgeTransport } from "@droid-web-display/scrcpy-protocol";

export type WebSocketFactory = (url: string) => WebSocket;

type LatencyMetrics = Record<string, number | string | boolean>;

function latencyMetrics(): LatencyMetrics {
  const root = globalThis as typeof globalThis & { __dwdLatencyMetrics?: LatencyMetrics };
  return root.__dwdLatencyMetrics ??= {};
}

export class WebSocketBridgeTransport implements BridgeTransport {
  readonly #sockets = new Set<WebSocket>();
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
      writable: writableToSocket(socket),
    };
  }

  public async close(): Promise<void> {
    for (const socket of this.#sockets) {
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close(1000, "transport closed");
      }
    }
    this.#sockets.clear();
    const metrics = latencyMetrics();
    metrics.controlSocketBufferedBytes = 0;
  }

  private async openReadableChannel(channel: "video" | "audio"): Promise<ReadableStream<Uint8Array>> {
    return readableFromSocket(await this.openSocket(channel), channel);
  }

  private async openSocket(channel: "video" | "audio" | "control"): Promise<WebSocket> {
    const url = `${this.baseUrl}/ws/v1/sessions/${encodeURIComponent(this.sessionId)}/${channel}?clientId=${encodeURIComponent(this.#clientId)}`;
    const socket = this.socketFactory(url);
    socket.binaryType = "arraybuffer";
    this.#sockets.add(socket);
    await waitForOpen(socket);
    socket.addEventListener("close", () => this.#sockets.delete(socket), { once: true });
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

function readableFromSocket(socket: WebSocket, channel: "video" | "audio" | "control"): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      const onMessage = (event: MessageEvent<ArrayBuffer | Blob>) => {
        const metrics = latencyMetrics();
        metrics[`${channel}SocketMessages`] = Number(metrics[`${channel}SocketMessages`] ?? 0) + 1;
        if (event.data instanceof ArrayBuffer) {
          metrics[`${channel}SocketLastMessageBytes`] = event.data.byteLength;
          controller.enqueue(new Uint8Array(event.data));
        } else if (event.data instanceof Blob) {
          metrics[`${channel}SocketLastMessageBytes`] = event.data.size;
          void event.data.arrayBuffer().then((value) => controller.enqueue(new Uint8Array(value))).catch((error) => controller.error(error));
        } else {
          controller.error(new Error("Expected binary WebSocket frame"));
        }
      };
      const onClose = (event: CloseEvent) => {
        cleanup();
        if (event.code === 1000) controller.close();
        else controller.error(new Error(`WebSocket closed (${event.code}: ${event.reason})`));
      };
      const onError = () => {
        cleanup();
        controller.error(new Error("WebSocket transport error"));
      };
      const cleanup = () => {
        socket.removeEventListener("message", onMessage as EventListener);
        socket.removeEventListener("close", onClose);
        socket.removeEventListener("error", onError);
      };
      socket.addEventListener("message", onMessage as EventListener);
      socket.addEventListener("close", onClose);
      socket.addEventListener("error", onError);
    },
    cancel() {
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close(1000, "reader cancelled");
      }
    },
  });
}

function writableToSocket(socket: WebSocket): WritableStream<Uint8Array> {
  // Control frames are tiny. A megabyte-scale backlog is unacceptable for an
  // interactive pointer/keyboard path, so apply backpressure while the browser
  // has more than 64 KiB queued for the socket.
  const maximumBufferedBytes = 64 * 1024;
  return new WritableStream<Uint8Array>({
    async write(chunk) {
      if (socket.readyState !== WebSocket.OPEN) {
        throw new Error("Control WebSocket is not open");
      }
      while (socket.bufferedAmount > maximumBufferedBytes) {
        latencyMetrics().controlBackpressureWaits = Number(latencyMetrics().controlBackpressureWaits ?? 0) + 1;
        await new Promise((resolve) => setTimeout(resolve, 1));
        if (socket.readyState !== WebSocket.OPEN) throw new Error("Control WebSocket closed during backpressure wait");
      }
      socket.send(chunk);
      const metrics = latencyMetrics();
      metrics.controlSocketBufferedBytes = socket.bufferedAmount;
      metrics.controlSocketPeakBufferedBytes = Math.max(
        Number(metrics.controlSocketPeakBufferedBytes ?? 0),
        socket.bufferedAmount,
      );
    },
    close() {
      latencyMetrics().controlSocketBufferedBytes = 0;
      if (socket.readyState === WebSocket.OPEN) socket.close(1000, "control writer closed");
    },
    abort(reason) {
      latencyMetrics().controlSocketBufferedBytes = 0;
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close(1011, String(reason ?? "control writer aborted"));
      }
    },
  });
}
