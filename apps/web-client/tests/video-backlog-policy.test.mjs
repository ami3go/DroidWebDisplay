import test from "node:test";
import assert from "node:assert/strict";
import { decoderBacklogAction } from "../dist/assets/video-backlog-policy.js";

test("startup backlog preserves the first queued keyframe", () => {
  assert.equal(decoderBacklogAction(3, 4, false, false), "decode");
  assert.equal(decoderBacklogAction(4, 4, false, false), "drop-delta");
});

test("startup may recover when a fresh keyframe is available", () => {
  assert.equal(decoderBacklogAction(4, 4, false, true), "recover");
});

test("normal low-latency recovery resumes after first decoder output", () => {
  assert.equal(decoderBacklogAction(4, 4, true, false), "recover");
});
