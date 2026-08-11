import test from "node:test";
import assert from "node:assert/strict";
import { extractH264DecoderConfiguration, splitAnnexBNalUnits } from "../dist/src/versions/v4_1/h264.js";
import { InvalidProtocolValueError } from "../dist/src/common/errors.js";

test("Annex B SPS/PPS configuration is extracted for WebCodecs", () => {
  const data = new Uint8Array([
    0, 0, 0, 1, 0x67, 0x64, 0x00, 0x28, 0xaa,
    0, 0, 1, 0x68, 0xee, 0x3c, 0x80,
  ]);
  const config = extractH264DecoderConfiguration(data);
  assert.equal(config.codec, "avc1.640028");
  assert.equal(config.format, "annexb");
  assert.equal(config.sequenceParameterSets.length, 1);
  assert.equal(config.pictureParameterSets.length, 1);
  assert.deepEqual([...splitAnnexBNalUnits(data)[1]], [0x68, 0xee, 0x3c, 0x80]);
});

test("configuration without SPS/PPS is rejected", () => {
  assert.throws(() => extractH264DecoderConfiguration(new Uint8Array([0, 0, 1, 0x65, 1])), InvalidProtocolValueError);
});
