import test from "node:test";
import assert from "node:assert/strict";
import { decoderBacklogAction } from "../dist/assets/video-backlog-policy.js";

test("small decoder jitter does not trigger recovery", () => {
  assert.equal(decoderBacklogAction(4, 4, true, false), "decode");
  assert.equal(decoderBacklogAction(11, 4, true, false), "decode");
});

test("startup backlog preserves the first queued keyframe", () => {
  assert.equal(decoderBacklogAction(11, 4, false, false), "decode");
  assert.equal(decoderBacklogAction(12, 4, false, false), "drop-delta");
});

test("delta-frame backlog never resets an already-running decoder", () => {
  assert.equal(decoderBacklogAction(12, 4, true, false), "drop-delta");
  assert.equal(decoderBacklogAction(24, 4, true, false), "drop-delta");
});

test("backlog recovery is allowed only when a fresh keyframe is available", () => {
  assert.equal(decoderBacklogAction(12, 4, false, true), "recover");
  assert.equal(decoderBacklogAction(12, 4, true, true), "recover");
});

test("callers may request a threshold above the safety floor", () => {
  assert.equal(decoderBacklogAction(15, 16, true, false), "decode");
  assert.equal(decoderBacklogAction(16, 16, true, false), "drop-delta");
});
