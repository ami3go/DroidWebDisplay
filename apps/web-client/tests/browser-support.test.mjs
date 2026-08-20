import test from "node:test";
import assert from "node:assert/strict";
import { browserName, inspectBrowserCapabilities } from "../dist/assets/browser-support.js";
import { decoderBacklogAction } from "../dist/assets/video-renderer.js";

test("reports all mandatory Chromium/WebCodecs capabilities", () => {
  const report = inspectBrowserCapabilities({
    WebSocket: class {},
    ReadableStream: class {},
    WritableStream: class {},
    VideoDecoder: class {},
    EncodedVideoChunk: class {},
    AudioDecoder: class {},
    EncodedAudioChunk: class {},
    AudioContext: class {},
    navigator: { userAgent: "Mozilla/5.0 Chrome/150.0.0.0 Safari/537.36", platform: "Win32", hardwareConcurrency: 8 },
  });
  assert.equal(report.supported, true);
  assert.deepEqual(report.missing, []);
  assert.equal(report.audioSupported, true);
  assert.deepEqual(report.missingAudio, []);
  assert.equal(report.browserName, "Chrome 150.0.0.0");
  assert.equal(report.platform, "Win32");
  assert.equal(report.hardwareConcurrency, 8);
});

test("extracts Edge before the embedded Chromium token", () => {
  assert.equal(
    browserName("Mozilla/5.0 Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0"),
    "Edge 150.0.0.0",
  );
});

test("rejects a browser without WebCodecs", () => {
  const report = inspectBrowserCapabilities({
    WebSocket: class {},
    ReadableStream: class {},
    WritableStream: class {},
    EncodedVideoChunk: class {},
  });
  assert.equal(report.supported, false);
  assert.deepEqual(report.missing, ["VideoDecoder"]);
});

test("reports optional audio independently from mandatory video support", () => {
  const report = inspectBrowserCapabilities({
    WebSocket: class {},
    ReadableStream: class {},
    WritableStream: class {},
    VideoDecoder: class {},
    EncodedVideoChunk: class {},
  });
  assert.equal(report.supported, true);
  assert.equal(report.audioSupported, false);
  assert.deepEqual(report.missingAudio, ["AudioDecoder", "EncodedAudioChunk", "AudioContext"]);
});

test("decoder backlog never drops an arbitrary H.264 delta frame", () => {
  assert.equal(decoderBacklogAction(9, false), "decode");
  assert.equal(decoderBacklogAction(100, false), "decode");
});

test("decoder backlog recovery is allowed only at a fresh keyframe", () => {
  assert.equal(decoderBacklogAction(8, true), "decode");
  assert.equal(decoderBacklogAction(9, true), "recover-at-keyframe");
});
