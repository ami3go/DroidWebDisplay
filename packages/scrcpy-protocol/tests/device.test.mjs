import test from "node:test";
import assert from "node:assert/strict";
import { AsyncByteReader } from "../dist/src/common/async-byte-reader.js";
import { InvalidProtocolValueError, TruncatedStreamError } from "../dist/src/common/errors.js";
import { DeviceMessageParser, DeviceMessageType } from "../dist/src/versions/v4_1/device.js";
import { concat, streamFromChunks, u32, u64 } from "./helpers.mjs";

test("device clipboard and ack messages parse across arbitrary chunks", async () => {
  const text = new TextEncoder().encode("hello");
  const bytes = concat(new Uint8Array([0]), u32(text.length), text, new Uint8Array([1]), u64(99n));
  const parser = new DeviceMessageParser(new AsyncByteReader(streamFromChunks(bytes.slice(0, 2), bytes.slice(2, 9), bytes.slice(9))));
  assert.deepEqual(await parser.read(), { type: DeviceMessageType.Clipboard, text: "hello" });
  assert.deepEqual(await parser.read(), { type: DeviceMessageType.AckClipboard, sequence: 99n });
});

test("unknown and truncated device messages fail deterministically", async () => {
  const unknown = new DeviceMessageParser(new AsyncByteReader(streamFromChunks(new Uint8Array([99]))));
  await assert.rejects(unknown.read(), InvalidProtocolValueError);

  const truncated = new DeviceMessageParser(new AsyncByteReader(streamFromChunks(new Uint8Array([0, 0, 0, 0, 5, 1]))));
  await assert.rejects(truncated.read(), TruncatedStreamError);
});
