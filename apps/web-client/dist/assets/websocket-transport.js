function latencyMetrics() {
    const root = globalThis;
    return root.__dwdLatencyMetrics ??= {};
}
export class WebSocketBridgeTransport {
    sessionId;
    baseUrl;
    socketFactory;
    #sockets = new Set();
    #clientId = crypto.randomUUID();
    constructor(sessionId, baseUrl = websocketBaseUrl(), socketFactory = (url) => new WebSocket(url)) {
        this.sessionId = sessionId;
        this.baseUrl = baseUrl;
        this.socketFactory = socketFactory;
    }
    async openVideoChannel() {
        return this.openReadableChannel("video");
    }
    async openAudioChannel() {
        return this.openReadableChannel("audio");
    }
    async openControlChannel() {
        const socket = await this.openSocket("control");
        return {
            readable: readableFromSocket(socket, "control"),
            writable: writableToSocket(socket),
        };
    }
    async close() {
        for (const socket of this.#sockets) {
            if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
                socket.close(1000, "transport closed");
            }
        }
        this.#sockets.clear();
        const metrics = latencyMetrics();
        metrics.controlSocketBufferedBytes = 0;
    }
    async openReadableChannel(channel) {
        return readableFromSocket(await this.openSocket(channel), channel);
    }
    async openSocket(channel) {
        const url = `${this.baseUrl}/ws/v1/sessions/${encodeURIComponent(this.sessionId)}/${channel}?clientId=${encodeURIComponent(this.#clientId)}`;
        const socket = this.socketFactory(url);
        socket.binaryType = "arraybuffer";
        this.#sockets.add(socket);
        await waitForOpen(socket);
        socket.addEventListener("close", () => this.#sockets.delete(socket), { once: true });
        return socket;
    }
}
function websocketBaseUrl() {
    const scheme = location.protocol === "https:" ? "wss:" : "ws:";
    return `${scheme}//${location.host}`;
}
function waitForOpen(socket) {
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
        const onClose = (event) => {
            cleanup();
            reject(new Error(`WebSocket closed before opening (${event.code}: ${event.reason})`));
        };
        socket.addEventListener("open", onOpen, { once: true });
        socket.addEventListener("error", onError, { once: true });
        socket.addEventListener("close", onClose, { once: true });
    });
}
function readableFromSocket(socket, channel) {
    return new ReadableStream({
        start(controller) {
            const onMessage = (event) => {
                const metrics = latencyMetrics();
                metrics[`${channel}SocketMessages`] = Number(metrics[`${channel}SocketMessages`] ?? 0) + 1;
                if (event.data instanceof ArrayBuffer) {
                    metrics[`${channel}SocketLastMessageBytes`] = event.data.byteLength;
                    controller.enqueue(new Uint8Array(event.data));
                }
                else if (event.data instanceof Blob) {
                    metrics[`${channel}SocketLastMessageBytes`] = event.data.size;
                    void event.data.arrayBuffer().then((value) => controller.enqueue(new Uint8Array(value))).catch((error) => controller.error(error));
                }
                else {
                    controller.error(new Error("Expected binary WebSocket frame"));
                }
            };
            const onClose = (event) => {
                cleanup();
                if (event.code === 1000)
                    controller.close();
                else
                    controller.error(new Error(`WebSocket closed (${event.code}: ${event.reason})`));
            };
            const onError = () => {
                cleanup();
                controller.error(new Error("WebSocket transport error"));
            };
            const cleanup = () => {
                socket.removeEventListener("message", onMessage);
                socket.removeEventListener("close", onClose);
                socket.removeEventListener("error", onError);
            };
            socket.addEventListener("message", onMessage);
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
function writableToSocket(socket) {
    // Control frames are tiny. A megabyte-scale backlog is unacceptable for an
    // interactive pointer/keyboard path, so apply backpressure while the browser
    // has more than 64 KiB queued for the socket.
    const maximumBufferedBytes = 64 * 1024;
    return new WritableStream({
        async write(chunk) {
            if (socket.readyState !== WebSocket.OPEN) {
                throw new Error("Control WebSocket is not open");
            }
            while (socket.bufferedAmount > maximumBufferedBytes) {
                latencyMetrics().controlBackpressureWaits = Number(latencyMetrics().controlBackpressureWaits ?? 0) + 1;
                await new Promise((resolve) => setTimeout(resolve, 1));
                if (socket.readyState !== WebSocket.OPEN)
                    throw new Error("Control WebSocket closed during backpressure wait");
            }
            socket.send(chunk);
            const metrics = latencyMetrics();
            metrics.controlSocketBufferedBytes = socket.bufferedAmount;
            metrics.controlSocketPeakBufferedBytes = Math.max(Number(metrics.controlSocketPeakBufferedBytes ?? 0), socket.bufferedAmount);
        },
        close() {
            latencyMetrics().controlSocketBufferedBytes = 0;
            if (socket.readyState === WebSocket.OPEN)
                socket.close(1000, "control writer closed");
        },
        abort(reason) {
            latencyMetrics().controlSocketBufferedBytes = 0;
            if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
                socket.close(1011, String(reason ?? "control writer aborted"));
            }
        },
    });
}
//# sourceMappingURL=websocket-transport.js.map