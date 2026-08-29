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

/** Drive the real guard through the controller's two call sites: a manual copy
    request resets it (beginAndroidCopyRequest), and each inbound Clipboard
    message is offered to consume() before a completed manual copy arms it. */
function clipboardSequence(guard) {
  let pending = false;
  let clock = 1000;
  return {
    /** beginAndroidCopyRequest: user pressed Ctrl+C or clicked Copy. */
    requestCopy() {
      guard.reset();
      pending = true;
    },
    /** Returns the status the controller would show for one Clipboard message. */
    deliver(text) {
      clock += 100;
      if (guard.consume(text, clock)) return "suppressed";
      const wasManual = pending;
      pending = false;
      if (wasManual) guard.arm(text, clock);
      return wasManual ? "copied" : "synchronized";
    },
    /** The 1200 ms timer fires "not confirmed" only if nothing answered. */
    settle() {
      const outcome = pending ? "not-confirmed" : "answered";
      pending = false;
      return outcome;
    },
  };
}

test("repeating a manual copy of unchanged Android text still reports success", () => {
  const sequence = clipboardSequence(new ManualCopyDuplicateGuard(750));

  sequence.requestCopy();
  assert.equal(sequence.deliver("selected text"), "copied");
  assert.equal(sequence.settle(), "answered");

  // The patched server answers every explicit request, so an immediate second
  // copy of the same selection must not be mistaken for the first copy's echo.
  sequence.requestCopy();
  assert.equal(sequence.deliver("selected text"), "copied");
  assert.equal(sequence.settle(), "answered");
});

test("autosync echo of a manual copy stays suppressed", () => {
  const sequence = clipboardSequence(new ManualCopyDuplicateGuard(750));

  sequence.requestCopy();
  assert.equal(sequence.deliver("selected text"), "copied");
  assert.equal(sequence.deliver("selected text"), "suppressed");

  // A genuine later Android change is still reported.
  assert.equal(sequence.deliver("something else"), "synchronized");
});

test("manual copy duplicate guard can be reset between sessions", () => {
  const guard = new ManualCopyDuplicateGuard();
  guard.arm("selected text", 1000);
  guard.reset();

  assert.equal(guard.consume("selected text", 1001), false);
  assert.throws(() => new ManualCopyDuplicateGuard(0), /windowMs must be positive/);
});
