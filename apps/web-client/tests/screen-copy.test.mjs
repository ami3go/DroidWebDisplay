import test from "node:test";
import assert from "node:assert/strict";
import { screenCopyShortcut } from "../dist/assets/screen-copy.js";

test("screen copy shortcuts distinguish smart and forced image copy", () => {
  assert.equal(screenCopyShortcut({ key: "c", ctrlKey: true, metaKey: false, altKey: false, shiftKey: false }), "smart");
  assert.equal(screenCopyShortcut({ key: "C", ctrlKey: true, metaKey: false, altKey: false, shiftKey: true }), "image");
  assert.equal(screenCopyShortcut({ key: "c", ctrlKey: false, metaKey: true, altKey: false, shiftKey: true }), "image");
  assert.equal(screenCopyShortcut({ key: "c", ctrlKey: true, metaKey: false, altKey: true, shiftKey: false }), null);
  assert.equal(screenCopyShortcut({ key: "v", ctrlKey: true, metaKey: false, altKey: false, shiftKey: false }), null);
});
