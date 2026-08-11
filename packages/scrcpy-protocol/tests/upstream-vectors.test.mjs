import test from "node:test";
import assert from "node:assert/strict";
import {
  ControlMessageType,
  serializeControlMessage,
} from "../dist/src/versions/v4_1/control.js";
import {
  DeviceMessageParser,
  DeviceMessageType,
} from "../dist/src/versions/v4_1/device.js";
import { AsyncByteReader } from "../dist/src/common/async-byte-reader.js";
import { InvalidProtocolValueError } from "../dist/src/common/errors.js";
import { streamFromChunks } from "./helpers.mjs";

const bytes = (value) => [...value];

test("upstream v4.1 inject-keycode vector matches byte-for-byte", () => {
  assert.deepEqual(bytes(serializeControlMessage({
    type: ControlMessageType.InjectKeycode,
    action: 1,
    keycode: 0x42,
    repeat: 5,
    metaState: 0x41,
  })), [
    0x00, 0x01,
    0x00, 0x00, 0x00, 0x42,
    0x00, 0x00, 0x00, 0x05,
    0x00, 0x00, 0x00, 0x41,
  ]);
});

test("upstream v4.1 touch and scroll vectors match byte-for-byte", () => {
  assert.deepEqual(bytes(serializeControlMessage({
    type: ControlMessageType.InjectTouchEvent,
    action: 0,
    pointerId: 0x1234567887654321n,
    position: { x: 100, y: 200, screenWidth: 1080, screenHeight: 1920 },
    pressure: 1,
    actionButton: 1,
    buttons: 1,
  })), [
    0x02, 0x00,
    0x12, 0x34, 0x56, 0x78, 0x87, 0x65, 0x43, 0x21,
    0x00, 0x00, 0x00, 0x64, 0x00, 0x00, 0x00, 0xc8,
    0x04, 0x38, 0x07, 0x80,
    0xff, 0xff,
    0x00, 0x00, 0x00, 0x01,
    0x00, 0x00, 0x00, 0x01,
  ]);

  assert.deepEqual(bytes(serializeControlMessage({
    type: ControlMessageType.InjectScrollEvent,
    position: { x: 260, y: 1026, screenWidth: 1080, screenHeight: 1920 },
    horizontal: 16,
    vertical: -16,
    buttons: 1,
  })), [
    0x03,
    0x00, 0x00, 0x01, 0x04, 0x00, 0x00, 0x04, 0x02,
    0x04, 0x38, 0x07, 0x80,
    0x7f, 0xff, 0x80, 0x00,
    0x00, 0x00, 0x00, 0x01,
  ]);
});

test("upstream v4.1 clipboard, UHID and utility vectors match", () => {
  const encoder = new TextEncoder();
  assert.deepEqual(bytes(serializeControlMessage({
    type: ControlMessageType.SetClipboard,
    sequence: 0x0102030405060708n,
    paste: true,
    text: "hello, world!",
  })), [
    0x09,
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x01,
    0x00, 0x00, 0x00, 0x0d,
    ...encoder.encode("hello, world!"),
  ]);

  assert.deepEqual(bytes(serializeControlMessage({
    type: ControlMessageType.UhidCreate,
    id: 42,
    vendorId: 0x1234,
    productId: 0x5678,
    name: "ABC",
    reportDescriptor: new Uint8Array([1,2,3,4,5,6,7,8,9,10,11]),
  })), [
    0x0c, 0x00, 0x2a, 0x12, 0x34, 0x56, 0x78,
    0x03, 0x41, 0x42, 0x43,
    0x00, 0x0b, 1,2,3,4,5,6,7,8,9,10,11,
  ]);

  assert.deepEqual(bytes(serializeControlMessage({
    type: ControlMessageType.ResizeDisplay,
    width: 1920,
    height: 1080,
  })), [0x15, 0x07, 0x80, 0x04, 0x38]);

  assert.deepEqual(bytes(serializeControlMessage({
    type: ControlMessageType.ScanFile,
    path: "/sdcard/Download",
  })), [
    0x16, 0x00, 0x00, 0x00, 0x10,
    ...encoder.encode("/sdcard/Download"),
  ]);
});

test("upstream v4.1 device-message vectors parse byte-for-byte", async () => {
  const input = new Uint8Array([
    0x00, 0x00, 0x00, 0x00, 0x03, 0x41, 0x42, 0x43,
    0x01, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x02, 0x00, 0x2a, 0x00, 0x05, 1, 2, 3, 4, 5,
  ]);
  const parser = new DeviceMessageParser(new AsyncByteReader(streamFromChunks(input.slice(0, 4), input.slice(4, 13), input.slice(13))));
  assert.deepEqual(await parser.read(), { type: DeviceMessageType.Clipboard, text: "ABC" });
  assert.deepEqual(await parser.read(), { type: DeviceMessageType.AckClipboard, sequence: 0x0102030405060708n });
  assert.deepEqual(await parser.read(), { type: DeviceMessageType.UhidOutput, id: 42, data: new Uint8Array([1,2,3,4,5]) });
});

test("runtime-invalid control values are rejected instead of wrapping", () => {
  assert.throws(() => serializeControlMessage({
    type: ControlMessageType.InjectKeycode,
    action: 256,
    keycode: 1,
    repeat: 0,
    metaState: 0,
  }), InvalidProtocolValueError);
  assert.throws(() => serializeControlMessage({ type: 255 }), InvalidProtocolValueError);
});
