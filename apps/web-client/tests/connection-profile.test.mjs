import test from "node:test";
import assert from "node:assert/strict";
import {
  parsePortableConnectionProfile,
  portableConnectionProfile,
} from "../dist/assets/connection-profile-controller.js";

const stored = {
  schemaVersion: 1,
  id: "abc123",
  name: "S20 Daily",
  device: { serial: "R58N123456A", model: "SM-G980F" },
  display: {
    displayMode: "virtual",
    profileId: "low-latency",
    sizeMode: "fixed",
    width: 1280,
    height: 720,
    dpi: 220,
    startApp: "com.openai.chatgpt",
    forceStopBeforeLaunch: false,
    keepActive: true,
    systemDecorations: true,
    destroyContentOnClose: true,
    imePolicy: "local",
    preserveAspectRatio: true,
    videoBitRateMbps: 10,
    maxFps: 60,
  },
  audio: { enabled: false, muted: false, volume: 80 },
  clipboard: { automatic: false, maximumKiB: 128 },
  reconnect: { enabled: true, attempts: 5 },
  video: { encoderMode: "auto", encoder: null },
  createdAt: "2026-08-12T00:00:00Z",
  updatedAt: "2026-08-12T00:00:00Z",
  lastUsedAt: null,
  pin: "must-not-export",
};

test("portable profile export strips server metadata and unrelated fields", () => {
  const exported = portableConnectionProfile(stored);
  assert.equal(exported.kind, "droidwebdisplay-connection-profile");
  assert.equal(exported.exportVersion, 1);
  assert.equal(exported.profileSchemaVersion, 1);
  assert.equal(exported.profile.name, "S20 Daily");
  assert.equal(exported.profile.device.serial, "R58N123456A");
  assert.equal("id" in exported.profile, false);
  assert.equal("createdAt" in exported.profile, false);
  assert.equal("pin" in exported.profile, false);
});

test("portable profile round-trips the allowed connection settings", () => {
  const exported = portableConnectionProfile(stored);
  const parsed = parsePortableConnectionProfile(JSON.parse(JSON.stringify(exported)));
  assert.equal(parsed.name, "S20 Daily");
  assert.equal(parsed.display.profileId, "low-latency");
  assert.equal(parsed.display.maxFps, 60);
  assert.equal(parsed.audio.volume, 80);
  assert.equal(parsed.reconnect.attempts, 5);
  assert.deepEqual(parsed.video, { encoderMode: "auto", encoder: null });
});

test("direct schema-v1 stored profile can be imported without its server metadata", () => {
  const parsed = parsePortableConnectionProfile(stored);
  assert.equal(parsed.name, "S20 Daily");
  assert.equal(parsed.device.serial, "R58N123456A");
  assert.equal("id" in parsed, false);
});

test("newer and malformed profile files fail deterministically", () => {
  assert.throws(
    () => parsePortableConnectionProfile({ ...portableConnectionProfile(stored), profileSchemaVersion: 2 }),
    /newer DroidWebDisplay version/,
  );
  assert.throws(
    () => parsePortableConnectionProfile({ schemaVersion: 1, name: "Incomplete" }),
    /missing 'device'/,
  );
});
