import test from "node:test";
import assert from "node:assert/strict";
import { ManualCopyDuplicateGuard } from "../dist/assets/clipboard-events.js";

test("manual copy consumes one matching autosync duplicate", () => {
  const guard = new ManualCopyDuplicateGuard(750);
  guard.arm("selected text", 1000);

  assert.equal(guard.consume("selected text", 1100), true);
  assert.equal(guard.consume("selected text", 1101), false);
});

test("manual copy does not hide unrelated or expired clipboard messages", () => {
  const guard = new ManualCopyDuplicateGuard(750);
  guard.arm("selected text", 1000);

  assert.equal(guard.consume("new text", 1100), false);
  assert.equal(guard.consume("selected text", 1751), false);
});

test("manual copy duplicate guard can be reset between sessions", () => {
  const guard = new ManualCopyDuplicateGuard();
  guard.arm("selected text", 1000);
  guard.reset();

  assert.equal(guard.consume("selected text", 1001), false);
  assert.throws(() => new ManualCopyDuplicateGuard(0), /windowMs must be positive/);
});
