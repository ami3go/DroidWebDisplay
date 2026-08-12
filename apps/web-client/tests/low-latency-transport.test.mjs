import test from "node:test";
import assert from "node:assert/strict";
import { WebSocketBridgeTransport } from "../dist/assets/websocket-transport.js";

class FakeWebSocket extends EventTarget {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = FakeWebSocket.CONNECTING;
  binaryType = "blob";
  bufferedAmount = 0;
  closeCode = null;
  closeReason = "";
  sent = [];

  constructor(url) {
    super();
    this.url = url;
    queueMicrotask(() => {
      if (this.readyState !== FakeWebSocket.CONNECTING) return;
      this.readyState = FakeWebSocket.OPEN;
      this.dispatchEvent(new Event("open"));
    });
  }

  send(data) {
    this.sent.push(data);
  }

  close(code = 1000, reason = "") {
    if (this.readyState === FakeWebSocket.CLOSED) return;
    this.closeCode = code;
    this.closeReason = reason;
    this.readyState = FakeWebSocket.CLOSED;
    const event = new Event("close");
    Object.defineProperties(event, {
      code: { value: code },
      reason: { value: reason },
    });
    this.dispatchEvent(event);
  }

  message(data) {
    const event = new Event("message");
    Object.defineProperty(event, "data", { value: data });
    this.dispatchEvent(event);
  }
}

const originalWebSocket = globalThis.WebSocket;
globalThis.WebSocket = FakeWebSocket;

test.after(() => {
  if (originalWebSocket === undefined) delete globalThis.WebSocket;
  else globalThis.WebSocket = originalWebSocket;
});

test("video receive queue fails fast instead of accumulating stale bytes", async () => {
  globalThis.__dwdLatencyMetrics = {};
  const sockets = [];
  const transport = new WebSocketBridgeTransport(
    "session",
    "ws://example.test",
    (url) => {
      const socket = new FakeWebSocket(url);
      sockets.push(socket);
      return socket;
    },
  );

  await transport.openVideoChannel();
  const socket = sockets[0];
  const chunk = new Uint8Array(64 * 1024).buffer;

  // One chunk may sit in ReadableStream's own single-item queue. The explicit
  // transport queue is capped at 512 KiB, so enough additional chunks must
  // close the stream instead of building seconds of invisible latency.
  for (let index = 0; index < 10; index += 1) socket.message(chunk.slice(0));
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(socket.closeCode, 1013);
  assert.match(socket.closeReason, /video backlog exceeded/);
  assert.equal(globalThis.__dwdLatencyMetrics.videoSocketBacklogOverflows, 1);
  await transport.close();
  delete globalThis.__dwdLatencyMetrics;
});

test("Blob conversion cannot reorder WebSocket byte-stream chunks", async () => {
  const sockets = [];
  const transport = new WebSocketBridgeTransport(
    "session-order",
    "ws://example.test",
    (url) => {
      const socket = new FakeWebSocket(url);
      sockets.push(socket);
      return socket;
    },
  );

  const stream = await transport.openVideoChannel();
  const reader = stream.getReader();
  const socket = sockets[0];
  socket.message(new Blob([new Uint8Array([1])]));
  socket.message(new Uint8Array([2]).buffer);

  assert.deepEqual([...((await reader.read()).value ?? [])], [1]);
  assert.deepEqual([...((await reader.read()).value ?? [])], [2]);
  await reader.cancel();
  await transport.close();
});
