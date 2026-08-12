import test from "node:test";
import assert from "node:assert/strict";
import { ScrcpyV41Adapter } from "../dist/src/versions/v4_1/adapter.js";
import { ControlMessageType } from "../dist/src/versions/v4_1/control.js";
import { concat, streamFromChunks } from "./helpers.mjs";

function deviceName(name) {
  const result = new Uint8Array(64);
  result.set(new TextEncoder().encode(name));
  return result;
}

function controlOnlyTransport(written, writeDelayMs = 0) {
  return {
    sessionId: "low-latency-control",
    openVideoChannel: async () => null,
    openAudioChannel: async () => null,
    openControlChannel: async () => ({
      readable: streamFromChunks(concat(new Uint8Array([0]), deviceName("control-only"))),
      writable: new WritableStream({
        async write(chunk) {
          if (writeDelayMs) await new Promise((resolve) => setTimeout(resolve, writeDelayMs));
          written.push(chunk.slice());
        },
      }),
    }),
    close: async () => {},
  };
}

function move(pointerId, x) {
  return {
    type: ControlMessageType.InjectTouchEvent,
    action: 2,
    pointerId,
    position: { x, y: 10, screenWidth: 100, screenHeight: 100 },
    pressure: 1,
    actionButton: 0,
    buttons: 1,
  };
}

function readPointerId(bytes) {
  let value = 0n;
  for (let index = 2; index < 10; index += 1) value = (value << 8n) | BigInt(bytes[index]);
  return value;
}

function readX(bytes) {
  return (bytes[10] << 24) | (bytes[11] << 16) | (bytes[12] << 8) | bytes[13];
}

test("latest MOVE is retained independently for each pointer", async () => {
  const written = [];
  globalThis.__dwdLatencyMetrics = {};
  const session = await new ScrcpyV41Adapter().connect(controlOnlyTransport(written), {
    video: false,
    audio: false,
    control: true,
  });

  await session.sendControl(move(1n, 10));
  await session.sendControl(move(2n, 20));
  await session.sendControl(move(1n, 11));
  await session.sendControl(move(2n, 21));
  await session.sendControl({ type: ControlMessageType.RotateDevice });

  assert.equal(written.length, 3);
  assert.equal(written[0][0], ControlMessageType.InjectTouchEvent);
  assert.equal(written[1][0], ControlMessageType.InjectTouchEvent);
  assert.deepEqual([readPointerId(written[0]), readX(written[0])], [1n, 11]);
  assert.deepEqual([readPointerId(written[1]), readX(written[1])], [2n, 21]);
  assert.equal(written[2][0], ControlMessageType.RotateDevice);
  assert.equal(globalThis.__dwdLatencyMetrics.controlMovesCoalesced, 2);

  await session.close();
  delete globalThis.__dwdLatencyMetrics;
});

test("ordering barrier waits behind already queued control writes", async () => {
  const written = [];
  const session = await new ScrcpyV41Adapter().connect(controlOnlyTransport(written, 5), {
    video: false,
    audio: false,
    control: true,
  });

  await session.sendControl(move(7n, 70));
  const barrier = session.sendControl({ type: ControlMessageType.RotateDevice });
  await barrier;

  assert.equal(written.length, 2);
  assert.equal(written[0][0], ControlMessageType.InjectTouchEvent);
  assert.equal(written[1][0], ControlMessageType.RotateDevice);
  await session.close();
});
