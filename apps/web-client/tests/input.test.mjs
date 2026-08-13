import test from "node:test";
import assert from "node:assert/strict";
import { androidClipboardCopyMessage, androidKeyPress, clipboardMessage, clipboardShortcut, keyboardMessages, mapClientPoint, textInjectionMessages } from "../dist/assets/input.js";

test("maps pointer coordinates and clamps outside positions", () => {
  const rect = { left: 100, top: 50, width: 400, height: 800 };
  assert.deepEqual(mapClientPoint(300, 450, rect, { width: 1080, height: 2400 }), {
    x: 540,
    y: 1200,
    screenWidth: 1080,
    screenHeight: 2400,
  });
  assert.deepEqual(mapClientPoint(0, 5000, rect, { width: 2400, height: 1080 }), {
    x: 0,
    y: 1079,
    screenWidth: 2400,
    screenHeight: 1080,
  });
});

test("rotation dimensions immediately change coordinate mapping", () => {
  const rect = { left: 0, top: 0, width: 800, height: 400 };
  const position = mapClientPoint(400, 200, rect, { width: 2400, height: 1080 });
  assert.equal(position.x, 1200);
  assert.equal(position.y, 540);
});

test("keyboard and Android navigation messages are deterministic", () => {
  assert.deepEqual(keyboardMessages({ key: "a", ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, repeat: false }), [
    { type: 1, text: "a" },
  ]);
  assert.deepEqual(androidKeyPress(3), [
    { type: 0, action: 0, keycode: 3, repeat: 0, metaState: 0 },
    { type: 0, action: 1, keycode: 3, repeat: 0, metaState: 0 },
  ]);
});


test("legacy text fallback splits UTF-8 without breaking code points", () => {
  const text = "A".repeat(299) + "😀" + "B";
  const messages = textInjectionMessages(text, 300);
  assert.equal(messages.length, 2);
  assert.equal(messages[0].text, "A".repeat(299));
  assert.equal(messages[1].text, "😀B");
  assert.equal(messages.map((message) => message.text).join(""), text);
});


test("automatic clipboard synchronization can update Android without requesting paste", () => {
  assert.deepEqual(clipboardMessage("sync text", 7n, false), {
    type: 9,
    sequence: 7n,
    paste: false,
    text: "sync text",
  });
  assert.deepEqual(clipboardMessage("manual paste", 8n, true), {
    type: 9,
    sequence: 8n,
    paste: true,
    text: "manual paste",
  });
});


test("Ctrl+C stays explicit while Ctrl/Cmd+V is left to the native paste event", () => {
  assert.equal(clipboardShortcut({ key: "v", ctrlKey: true, metaKey: false, altKey: false }), null);
  assert.equal(clipboardShortcut({ key: "V", ctrlKey: false, metaKey: true, altKey: false }), null);
  assert.equal(clipboardShortcut({ key: "C", ctrlKey: true, metaKey: false, altKey: false }), "copy");
  assert.equal(clipboardShortcut({ key: "v", ctrlKey: false, metaKey: false, altKey: false }), null);
  assert.deepEqual(androidClipboardCopyMessage(), { type: 8, copyKey: 1 });
});
