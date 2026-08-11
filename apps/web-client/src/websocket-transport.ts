import type { BridgeTransport } from "@droid-web-display/scrcpy-protocol";

export type WebSocketFactory = (url: string) => WebSocket;

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
      readable: readableFromSocket(socket),
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
  }

  private async openReadableChannel(channel: "video" | "audio"): Promise<ReadableStream<Uint8Array>> {
    return readableFromSocket(await this.openSocket(channel));
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

function readableFromSocket(socket: WebSocket): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      const onMessage = (event: MessageEvent<ArrayBuffer | Blob>) => {
        if (event.data instanceof ArrayBuffer) {
          controller.enqueue(new Uint8Array(event.data));
        } else if (event.data instanceof Blob) {
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
  return new WritableStream<Uint8Array>({
    async write(chunk) {
      if (socket.readyState !== WebSocket.OPEN) {
        throw new Error("Control WebSocket is not open");
      }
      while (socket.bufferedAmount > 1024 * 1024) {
        await new Promise((resolve) => setTimeout(resolve, 5));
        if (socket.readyState !== WebSocket.OPEN) throw new Error("Control WebSocket closed during backpressure wait");
      }
      socket.send(chunk);
    },
    close() {
      if (socket.readyState === WebSocket.OPEN) socket.close(1000, "control writer closed");
    },
    abort(reason) {
      if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
        socket.close(1011, String(reason ?? "control writer aborted"));
      }
    },
  });
}
