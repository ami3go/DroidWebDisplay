import test from "node:test";
import assert from "node:assert/strict";
import {
  alignedFlexSize,
  buildSessionRequest,
  PHYSICAL_DISPLAY_DEFAULTS,
  validateDisplayForm,
  VIRTUAL_DISPLAY_PROFILES,
} from "../dist/assets/display-config.js";

const base = {
  displayMode: "virtual",
  profileId: "chatgpt-desktop",
  sizeMode: "fixed",
  width: 1600,
  height: 900,
  dpi: 240,
  startApp: "com.openai.chatgpt",
  forceStopBeforeLaunch: false,
  keepActive: true,
  systemDecorations: true,
  destroyContentOnClose: true,
  imePolicy: "local",
  preserveAspectRatio: true,
  videoBitRateMbps: 12,
  maxFps: 60,
};

test("recommended virtual-display profile is deterministic", () => {
  const profile = VIRTUAL_DISPLAY_PROFILES["chatgpt-desktop"];
  assert.equal(profile.width, 1600);
  assert.equal(profile.height, 900);
  assert.equal(profile.dpi, 240);
  assert.equal(profile.startApp, "com.openai.chatgpt");
});

test("low-latency profile targets 720p at 60 fps", () => {
  const profile = VIRTUAL_DISPLAY_PROFILES["low-latency"];
  assert.equal(profile.width, 1280);
  assert.equal(profile.height, 720);
  assert.equal(profile.videoBitRate, 10_000_000);
  assert.equal(profile.maxFps, 60);
});

test("physical mode uses the exported interactive defaults", () => {
  assert.deepEqual(PHYSICAL_DISPLAY_DEFAULTS, {
    videoCodec: "h264",
    maxSize: 1600,
    videoBitRate: 10_000_000,
    maxFps: 60,
  });
  const request = buildSessionRequest({ ...base, displayMode: "physical" }, "PHONE");
  assert.equal(request.videoCodec, PHYSICAL_DISPLAY_DEFAULTS.videoCodec);
  assert.equal(request.maxSize, PHYSICAL_DISPLAY_DEFAULTS.maxSize);
  assert.equal(request.videoBitRate, PHYSICAL_DISPLAY_DEFAULTS.videoBitRate);
  assert.equal(request.maxFps, PHYSICAL_DISPLAY_DEFAULTS.maxFps);
});

test("virtual-display request maps typed values", () => {
  const request = buildSessionRequest(base, "PHONE");
  assert.equal(request.displayMode, "virtual");
  assert.equal(request.maxSize, 0);
  assert.equal(request.videoBitRate, 12_000_000);
  assert.deepEqual(request.virtualDisplay.width, 1600);
  assert.deepEqual(request.virtualDisplay.imePolicy, "local");
});

test("invalid package and dimensions are rejected before API launch", () => {
  const errors = validateDisplayForm({ ...base, width: 500, startApp: "bad package" });
  assert.ok(errors.some((value) => value.includes("Width")));
  assert.ok(errors.some((value) => value.includes("package")));
});

test("flex resize is bounded, aligned and aspect-ratio aware", () => {
  const value = alignedFlexSize(1503, 901, 1600, 900, true);
  assert.equal(value.width % 16, 0);
  assert.equal(value.height % 16, 0);
  assert.ok(value.width >= 640 && value.width <= 3840);
  assert.ok(value.height >= 480 && value.height <= 2160);
});


test("virtual keyboard suppression maps to hide and never changes physical mode", () => {
  const virtualRequest = buildSessionRequest({ ...base, imePolicy: "hide" }, "PHONE");
  assert.equal(virtualRequest.virtualDisplay.imePolicy, "hide");
  const physicalRequest = buildSessionRequest({ ...base, displayMode: "physical", imePolicy: "hide" }, "PHONE");
  assert.equal(physicalRequest.displayMode, "physical");
  assert.equal("virtualDisplay" in physicalRequest, false);
});