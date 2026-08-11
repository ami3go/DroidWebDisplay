import test from "node:test";
import assert from "node:assert/strict";
import { ScrcpyV41Adapter } from "../dist/src/versions/v4_1/adapter.js";
import { CodecId, PACKET_FLAG_SESSION } from "../dist/src/versions/v4_1/constants.js";
import { ControlMessageType } from "../dist/src/versions/v4_1/control.js";
import { concat, streamFromChunks, u32, u64 } from "./helpers.mjs";

function deviceName(name) {
  const result = new Uint8Array(64);
  result.set(new TextEncoder().encode(name));
  return result;
}

test("adapter consumes first-channel handshake and writes control bytes", async () => {
  const video = concat(
    new Uint8Array([0]),
    deviceName("SM-G980F"),
    u32(CodecId.H264),
    u32(0x80000000), u32(1080), u32(2400),
    u64(1n), u32(1), new Uint8Array([0x65]),
  );
  const written = [];
  const transport = {
    sessionId: "test",
    openVideoChannel: async () => streamFromChunks(video.slice(0, 1), video.slice(1, 70), video.slice(70)),
    openAudioChannel: async () => null,
    openControlChannel: async () => ({
      readable: streamFromChunks(new Uint8Array([1]), u64(7n)),
      writable: new WritableStream({ write(chunk) { written.push(chunk.slice()); } }),
    }),
    close: async () => {},
  };
  const session = await new ScrcpyV41Adapter().connect(transport, { video: true, audio: false, control: true });
  assert.deepEqual(session.device, { name: "SM-G980F" });
  assert.equal(session.videoHeader.codec, "h264");
  assert.equal((await session.readVideoPacket()).data[0], 0x65);
  assert.deepEqual(await session.readDeviceMessage(), { type: 1, sequence: 7n });
  await session.sendControl({ type: ControlMessageType.RotateDevice });
  assert.deepEqual([...written[0]], [11]);
});

test("adapter rejects incompatible server metadata", () => {
  const adapter = new ScrcpyV41Adapter();
  assert.equal(adapter.validateServer({ scrcpyVersion: "4.1", adapterId: "scrcpy-4.1" }).compatible, true);
  assert.equal(adapter.validateServer({ scrcpyVersion: "4.0", adapterId: "scrcpy-4.1" }).compatible, false);
});


test("adapter opens enabled channels in upstream video-audio-control order", async () => {
  const order = [];
  const video = concat(new Uint8Array([0]), deviceName("order"), u32(CodecId.H264), u32(0x80000000), u32(100), u32(200));
  const audio = u32(CodecId.Opus);
  const transport = {
    sessionId: "order",
    openVideoChannel: async () => { order.push("video"); return streamFromChunks(video); },
    openAudioChannel: async () => { order.push("audio"); return streamFromChunks(audio); },
    openControlChannel: async () => { order.push("control"); return { readable: streamFromChunks(), writable: new WritableStream() }; },
    close: async () => {},
  };
  const session = await new ScrcpyV41Adapter().connect(transport, { video: true, audio: true, control: true });
  assert.deepEqual(order, ["video", "audio", "control"]);
  assert.equal(session.audioHeader.codec, "opus");
  await session.close();
});


test("explicitly disabled audio does not abort an otherwise valid session", async () => {
  const video = concat(new Uint8Array([0]), deviceName("audio-disabled"), u32(CodecId.H264), u32(0x80000000), u32(100), u32(200));
  const transport = {
    sessionId: "audio-disabled",
    openVideoChannel: async () => streamFromChunks(video),
    openAudioChannel: async () => streamFromChunks(u32(CodecId.Disabled)),
    openControlChannel: async () => ({ readable: streamFromChunks(), writable: new WritableStream() }),
    close: async () => {},
  };
  const session = await new ScrcpyV41Adapter().connect(transport, { video: true, audio: true, control: true });
  assert.equal(session.videoHeader.codec, "h264");
  assert.equal(session.audioHeader, null);
  await assert.rejects(session.readAudioPacket(), /audio channel is disabled/);
  await session.close();
});


test("audio configuration failure does not abort video or control", async () => {
  const video = concat(new Uint8Array([0]), deviceName("audio-config-error"), u32(CodecId.H264), u32(0x80000000), u32(100), u32(200));
  const transport = {
    sessionId: "audio-config-error",
    openVideoChannel: async () => streamFromChunks(video),
    openAudioChannel: async () => streamFromChunks(u32(CodecId.ConfigurationError)),
    openControlChannel: async () => ({ readable: streamFromChunks(), writable: new WritableStream() }),
    close: async () => {},
  };
  const session = await new ScrcpyV41Adapter().connect(transport, { video: true, audio: true, control: true });
  assert.equal(session.videoHeader.codec, "h264");
  assert.equal(session.audioHeader, null);
  await assert.rejects(session.readAudioPacket(), /audio channel is disabled/);
  await session.close();
});
