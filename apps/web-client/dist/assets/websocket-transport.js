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
            readable: readableFromSocket(socket),
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
    }
    async openReadableChannel(channel) {
        return readableFromSocket(await this.openSocket(channel));
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
function readableFromSocket(socket) {
    return new ReadableStream({
        start(controller) {
            const onMessage = (event) => {
                if (event.data instanceof ArrayBuffer) {
                    controller.enqueue(new Uint8Array(event.data));
                }
                else if (event.data instanceof Blob) {
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
    return new WritableStream({
        async write(chunk) {
            if (socket.readyState !== WebSocket.OPEN) {
                throw new Error("Control WebSocket is not open");
            }
            while (socket.bufferedAmount > 1024 * 1024) {
                await new Promise((resolve) => setTimeout(resolve, 5));
                if (socket.readyState !== WebSocket.OPEN)
                    throw new Error("Control WebSocket closed during backpressure wait");
            }
            socket.send(chunk);
        },
        close() {
            if (socket.readyState === WebSocket.OPEN)
                socket.close(1000, "control writer closed");
        },
        abort(reason) {
            if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
                socket.close(1011, String(reason ?? "control writer aborted"));
            }
        },
    });
}
//# sourceMappingURL=websocket-transport.js.map