import test from "node:test";
import assert from "node:assert/strict";
import {
  ControlMessageType,
  CopyKey,
  serializeControlMessage,
} from "../dist/src/versions/v4_1/control.js";

test("inject keycode serialization matches the 14-byte upstream layout", () => {
  const result = serializeControlMessage({
    type: ControlMessageType.InjectKeycode,
    action: 0,
    keycode: 4,
    repeat: 2,
    metaState: 0x1000,
  });
  assert.deepEqual([...result], [0, 0, 0, 0, 0, 4, 0, 0, 0, 2, 0, 0, 0x10, 0]);
});

test("touch message uses 32-byte big-endian layout", () => {
  const result = serializeControlMessage({
    type: ControlMessageType.InjectTouchEvent,
    action: 2,
    pointerId: 0xffffffffffffffffn,
    position: { x: 100, y: 200, screenWidth: 1080, screenHeight: 2400 },
    pressure: 1,
    actionButton: 1,
    buttons: 1,
  });
  assert.equal(result.length, 32);
  assert.equal(result[0], 2);
  assert.equal(result[1], 2);
  assert.deepEqual([...result.slice(2, 10)], Array(8).fill(0xff));
  assert.deepEqual([...result.slice(22, 24)], [0xff, 0xff]);
});

test("clipboard and empty messages serialize correctly", () => {
  const clipboard = serializeControlMessage({
    type: ControlMessageType.SetClipboard,
    sequence: 42n,
    paste: true,
    text: "ok",
  });
  assert.equal(clipboard[0], 9);
  assert.equal(clipboard.length, 16);
  assert.deepEqual([...clipboard.slice(-2)], [0x6f, 0x6b]);

  assert.deepEqual([...serializeControlMessage({ type: ControlMessageType.RotateDevice })], [11]);
  assert.deepEqual([...serializeControlMessage({ type: ControlMessageType.GetClipboard, copyKey: CopyKey.Copy })], [8, 1]);
});

test("scroll values are clamped to upstream range", () => {
  const result = serializeControlMessage({
    type: ControlMessageType.InjectScrollEvent,
    position: { x: 1, y: 2, screenWidth: 100, screenHeight: 200 },
    horizontal: 99,
    vertical: -99,
    buttons: 0,
  });
  assert.equal(result.length, 21);
  assert.deepEqual([...result.slice(13, 17)], [0x7f, 0xff, 0x80, 0x00]);
});
