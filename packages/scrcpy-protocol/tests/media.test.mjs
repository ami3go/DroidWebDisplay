import test from "node:test";
import assert from "node:assert/strict";
import { AsyncByteReader } from "../dist/src/common/async-byte-reader.js";
import { InvalidProtocolValueError, TruncatedStreamError } from "../dist/src/common/errors.js";
import { CodecId, PACKET_FLAG_CONFIG, PACKET_FLAG_KEY_FRAME, PACKET_FLAG_SESSION } from "../dist/src/versions/v4_1/constants.js";
import { ScrcpyMediaStreamParser } from "../dist/src/versions/v4_1/media.js";
import { concat, streamFromChunks, u32, u64 } from "./helpers.mjs";

function session(width, height, resized = false) {
  const flags = 0x80000000 | (resized ? 1 : 0);
  return concat(u32(flags >>> 0), u32(width), u32(height));
}

test("video header, configuration and key frame parse", async () => {
  const config = new Uint8Array([1, 2, 3]);
  const frame = new Uint8Array([4, 5]);
  const bytes = concat(
    u32(CodecId.H264),
    session(1080, 2400, true),
    u64(PACKET_FLAG_CONFIG), u32(config.length), config,
    u64(PACKET_FLAG_KEY_FRAME | 1234n), u32(frame.length), frame,
  );
  const parser = new ScrcpyMediaStreamParser(
    new AsyncByteReader(streamFromChunks(bytes.slice(0, 3), bytes.slice(3, 17), bytes.slice(17))),
    { kind: "video" },
  );
  assert.deepEqual(await parser.readHeader(), {
    codecId: CodecId.H264,
    codec: "h264",
    session: { width: 1080, height: 2400, clientResized: true },
  });
  assert.deepEqual(await parser.readPacket(), { data: config, pts: null, configuration: true, keyFrame: false });
  assert.deepEqual(await parser.readPacket(), { data: frame, pts: 1234n, configuration: false, keyFrame: true });
});

test("malformed video session and zero-length packets are rejected", async () => {
  const notSession = concat(u32(CodecId.H264), u64(0n), u32(1));
  const parser = new ScrcpyMediaStreamParser(new AsyncByteReader(streamFromChunks(notSession)), { kind: "video" });
  await assert.rejects(parser.readHeader(), InvalidProtocolValueError);

  const zero = concat(u32(CodecId.H264), session(100, 100), u64(1n), u32(0));
  const zeroParser = new ScrcpyMediaStreamParser(new AsyncByteReader(streamFromChunks(zero)), { kind: "video" });
  await zeroParser.readHeader();
  await assert.rejects(zeroParser.readPacket(), InvalidProtocolValueError);
});

test("truncated packet payload reports truncation", async () => {
  const bytes = concat(u32(CodecId.H264), session(100, 100), u64(2n), u32(4), new Uint8Array([1]));
  const parser = new ScrcpyMediaStreamParser(new AsyncByteReader(streamFromChunks(bytes)), { kind: "video" });
  await parser.readHeader();
  await assert.rejects(parser.readPacket(), TruncatedStreamError);
});


test("rotation session packet is accepted and updates video dimensions", async () => {
  const config = new Uint8Array([9, 8, 7]);
  const frame = new Uint8Array([6, 5]);
  const bytes = concat(
    u32(CodecId.H264),
    session(1080, 2400),
    session(2400, 1080, true),
    u64(PACKET_FLAG_CONFIG), u32(config.length), config,
    u64(PACKET_FLAG_KEY_FRAME | 44n), u32(frame.length), frame,
  );
  const parser = new ScrcpyMediaStreamParser(new AsyncByteReader(streamFromChunks(bytes)), { kind: "video" });
  await parser.readHeader();
  assert.deepEqual(await parser.readPacket(), {
    data: new Uint8Array(),
    pts: null,
    configuration: false,
    keyFrame: false,
    session: { width: 2400, height: 1080, clientResized: true },
  });
  assert.deepEqual(await parser.readPacket(), { data: config, pts: null, configuration: true, keyFrame: false });
  assert.deepEqual(await parser.readPacket(), { data: frame, pts: 44n, configuration: false, keyFrame: true });
});
