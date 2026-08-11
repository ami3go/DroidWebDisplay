import test from "node:test";
import assert from "node:assert/strict";
import { inspectBrowserCapabilities } from "../dist/assets/browser-support.js";

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
    navigator: { userAgent: "Chromium test" },
  });
  assert.equal(report.supported, true);
  assert.deepEqual(report.missing, []);
  assert.equal(report.audioSupported, true);
  assert.deepEqual(report.missingAudio, []);
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
