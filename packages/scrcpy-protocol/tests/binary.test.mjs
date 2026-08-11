import test from "node:test";
import assert from "node:assert/strict";
import {
  encodeUtf8Truncated,
  floatToI16Fixed,
  floatToU16Fixed,
  readI16be,
} from "../dist/src/common/binary.js";

test("UTF-8 truncation never splits a code point", () => {
  assert.equal(new TextDecoder().decode(encodeUtf8Truncated("A€B", 4)), "A€");
  assert.equal(new TextDecoder().decode(encodeUtf8Truncated("😀X", 4)), "😀");
});

test("fixed point conversion matches scrcpy boundaries", () => {
  assert.equal(floatToU16Fixed(0), 0);
  assert.equal(floatToU16Fixed(1), 0xffff);
  assert.equal(floatToI16Fixed(-1), -0x8000);
  assert.equal(floatToI16Fixed(1), 0x7fff);
  assert.equal(readI16be(new Uint8Array([0x80, 0x00])), -0x8000);
});
