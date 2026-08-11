#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { AsyncByteReader } from "../dist/src/common/async-byte-reader.js";
import { TruncatedStreamError } from "../dist/src/common/errors.js";
import { readDummyByte, readDeviceInfo } from "../dist/src/versions/v4_1/handshake.js";
import { ScrcpyMediaStreamParser } from "../dist/src/versions/v4_1/media.js";
import { extractH264DecoderConfiguration } from "../dist/src/versions/v4_1/h264.js";

function streamFromBytes(data) {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(data);
      controller.close();
    },
  });
}

function parseArguments(argv) {
  const result = { path: null, packetCount: null };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--packet-count") {
      const raw = argv[++index];
      const count = Number(raw);
      if (!Number.isInteger(count) || count < 1 || count > 10000) {
        throw new Error(`invalid --packet-count value: ${raw}`);
      }
      result.packetCount = count;
    } else if (!result.path) {
      result.path = value;
    } else {
      throw new Error(`unexpected argument: ${value}`);
    }
  }
  return result;
}

async function inspect(path, packetCount) {
  const data = new Uint8Array(await readFile(path));
  const reader = new AsyncByteReader(streamFromBytes(data), { label: `fixture ${path}` });
  await readDummyByte(reader);
  const device = await readDeviceInfo(reader);
  const parser = new ScrcpyMediaStreamParser(reader, { kind: "video", maximumPacketSize: 64 * 1024 * 1024 });
  const header = await parser.readHeader();
  const packets = [];
  let partialTail = false;
  const limit = packetCount ?? 100;
  for (let index = 0; index < limit; index += 1) {
    try {
      const packet = await parser.readPacket();
      const entry = {
        length: packet.data.byteLength,
        pts: packet.pts === null ? null : packet.pts.toString(),
        configuration: packet.configuration,
        keyFrame: packet.keyFrame,
      };
      if (packet.configuration && header.codec === "h264") {
        try {
          const config = extractH264DecoderConfiguration(packet.data);
          entry.decoderConfig = {
            codec: config.codec,
            format: config.format,
            spsCount: config.sequenceParameterSets.length,
            ppsCount: config.pictureParameterSets.length,
          };
        } catch (error) {
          entry.decoderConfigError = error instanceof Error ? error.message : String(error);
        }
      }
      packets.push(entry);
    } catch (error) {
      if (error instanceof TruncatedStreamError) {
        partialTail = true;
        break;
      }
      throw error;
    }
  }
  const completeRequestedPackets = packetCount === null || packets.length === packetCount;
  return {
    status: packets.length > 0 && completeRequestedPackets ? "PASS" : "FAIL",
    file: resolve(path),
    bytes: data.byteLength,
    device,
    header,
    packets,
    requestedPacketCount: packetCount,
    partialTail,
  };
}

let parsed;
try {
  parsed = parseArguments(process.argv.slice(2));
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(2);
}
if (!parsed.path) {
  console.error("Usage: node tools/inspect-fixture.mjs <raw-video-channel.bin> [--packet-count N]");
  process.exit(2);
}
try {
  const result = await inspect(parsed.path, parsed.packetCount);
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.status === "PASS" ? 0 : 1);
} catch (error) {
  console.error(JSON.stringify({
    status: "FAIL",
    file: resolve(parsed.path),
    error: error instanceof Error ? error.message : String(error),
    errorType: error instanceof Error ? error.name : typeof error,
  }, null, 2));
  process.exit(1);
}
