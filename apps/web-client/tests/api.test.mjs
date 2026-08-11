import test from "node:test";
import assert from "node:assert/strict";
import { BridgeApi, BridgeApiError } from "../dist/assets/api.js";

test("session request uses the versioned API and approved defaults", async () => {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({ sessionId: "S", serial: "P", state: "running", channels: ["video", "control"], options: {} }), {
      status: 201,
      headers: { "content-type": "application/json" },
    });
  };
  const api = new BridgeApi("http://bridge", fetchImpl);
  await api.startSession({ serial: "PHONE" });
  assert.equal(calls[0].url, "http://bridge/api/v1/sessions");
  const body = JSON.parse(calls[0].init.body);
  assert.equal(body.serial, "PHONE");
  assert.equal(body.videoCodec, "h264");
  assert.equal(body.audio, false);
});

test("API errors preserve HTTP status and server details", async () => {
  const api = new BridgeApi("", async () => new Response(JSON.stringify({ error: { message: "not ready" } }), {
    status: 409,
    headers: { "content-type": "application/json" },
  }));
  await assert.rejects(api.devices(), (error) => error instanceof BridgeApiError && error.status === 409 && error.message === "not ready");
});


test("default fetch preserves the Window/global binding", async () => {
  const originalFetch = globalThis.fetch;
  try {
    globalThis.fetch = function (url) {
      assert.equal(this, globalThis);
      return Promise.resolve(new Response(JSON.stringify({ devices: [] }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }));
    };
    const api = new BridgeApi();
    const result = await api.devices();
    assert.deepEqual(result, { devices: [] });
  } finally {
    globalThis.fetch = originalFetch;
  }
});


test("file transfer API uses structured versioned endpoints", async () => {
  const calls = [];
  const api = new BridgeApi("", async (url, init) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify({ transferId: "T1", state: "queued" }), { status: 202, headers: { "content-type": "application/json" } });
  });
  const file = new File(["data"], "demo.txt", { type: "text/plain" });
  await api.uploadFile({ serial: "PHONE", file, destinationPath: "/sdcard/Download", duplicatePolicy: "rename" });
  assert.equal(calls[0].url, "/api/v1/transfers/upload");
  assert.equal(calls[0].init.method, "POST");
  assert.ok(calls[0].init.body instanceof FormData);
});

test("automatic download API uses persistent versioned endpoints", async () => {
  const calls = [];
  const api = new BridgeApi("", async (url, init) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify({ schemaVersion: 1, config: {}, runtime: {}, files: [], processedFingerprints: 0 }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
  await api.configureAutoDownload({
    enabled: true,
    pcToAndroidEnabled: true,
    serial: "PHONE",
    sourcePath: "/sdcard/Download",
    destinationProfile: "default-downloads",
    duplicatePolicy: "rename",
    uploadDuplicatePolicy: "overwrite",
    scanIntervalSeconds: 2,
    stabilitySeconds: 3,
    stabilityObservations: 3,
    includeExisting: false,
    includeExistingPc: false,
    deleteAfterVerified: false,
  });
  assert.equal(calls[0].url, "/api/v1/auto-download");
  assert.equal(calls[0].init.method, "PUT");
  const body = JSON.parse(calls[0].init.body);
  assert.equal(body.sourcePath, "/sdcard/Download");
  assert.equal(body.pcToAndroidEnabled, true);
  assert.equal(body.uploadDuplicatePolicy, "overwrite");
  await api.scanAutoDownload();
  assert.equal(calls[1].url, "/api/v1/auto-download/scan");
});

test("running-app API lists GUI tasks and requests relocation to a virtual display", async () => {
  const calls = [];
  const api = new BridgeApi("", async (url, init) => {
    calls.push({ url: String(url), init });
    const payload = String(url).includes("running-apps")
      ? { serial: "PHONE", apps: [], moveStrategy: "start-activity-on-display" }
      : { status: "moved", moved: true, verified: true, sessionId: "S", displayId: 299, app: {}, strategy: "start-activity-on-display" };
    return new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });
  });
  await api.runningApps("PHONE");
  assert.equal(calls[0].url, "/api/v1/devices/PHONE/running-apps");
  await api.moveRunningApp({ sessionId: "S", taskId: 42, componentName: "com.example.notes/.MainActivity" });
  assert.equal(calls[1].url, "/api/v1/sessions/S/virtual-display/move-running-app");
  assert.equal(calls[1].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[1].init.body), { taskId: 42, componentName: "com.example.notes/.MainActivity" });
});

test("authentication API keeps setup public and adds CSRF to protected writes", async () => {
  const calls = [];
  const api = new BridgeApi("", async (url, init) => {
    calls.push({ url: String(url), init });
    const path = String(url);
    const payload = path.endsWith("/auth/status")
      ? {
        configured: true,
        authenticated: true,
        trustModel: "pc-local",
        phoneAuthoritative: false,
        csrfToken: "csrf-test-token",
        currentSession: { sessionId: "S1" },
        durationChoices: ["browser-session", "1-hour", "1-day", "1-week", "1-month", "1-year", "forever", "custom"],
        customDuration: { minimumSeconds: 300, maximumSeconds: 315360000 },
      }
      : { schemaVersion: 1, config: {}, runtime: {}, files: [], processedFingerprints: 0 };
    return new Response(JSON.stringify(payload), { status: 200, headers: { "content-type": "application/json" } });
  });
  await api.authStatus();
  await api.resetAutoDownload();
  assert.equal(calls[0].url, "/api/v1/auth/status");
  assert.equal(calls[0].init.credentials, "same-origin");
  assert.equal(new Headers(calls[0].init.headers).has("x-droidwebdisplay-csrf"), false);
  assert.equal(new Headers(calls[1].init.headers).get("x-droidwebdisplay-csrf"), "csrf-test-token");
});

test("authentication setup supports every required trust choice", async () => {
  const choices = ["browser-session", "1-hour", "1-day", "1-week", "1-month", "1-year", "forever", "custom"];
  const calls = [];
  const api = new BridgeApi("", async (url, init) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify({
      configured: true, authenticated: true, trustModel: "pc-local", phoneAuthoritative: false,
      csrfToken: "csrf", currentSession: { sessionId: "S" }, durationChoices: choices,
      customDuration: { minimumSeconds: 300, maximumSeconds: 315360000 },
    }), { status: 201, headers: { "content-type": "application/json" } });
  });
  await api.authSetup({ pin: "1234", confirmPin: "1234", duration: "custom", customSeconds: 600 });
  assert.equal(calls[0].url, "/api/v1/auth/setup");
  const body = JSON.parse(calls[0].init.body);
  assert.equal(body.customSeconds, 600);
  assert.equal(new Headers(calls[0].init.headers).has("x-droidwebdisplay-csrf"), false);
});

test("network access API validates and applies authenticated HTTPS configuration", async () => {
  const calls = [];
  const api = new BridgeApi("", async (url, init) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify({ valid: true, applied: true, url: "https://192.168.1.20:8765" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
  const config = {
    mode: "lan-https",
    bindAddress: "192.168.1.20",
    port: 8765,
    allowedNetworks: ["192.168.1.0/24"],
    certificateSource: "generated",
    certificateValidityDays: 365,
    manageFirewall: false,
    currentPin: "123456",
  };
  await api.validateNetworkConfig(config);
  await api.applyNetworkConfig(config);
  assert.equal(calls[0].url, "/api/v1/network/validate");
  assert.equal(calls[1].url, "/api/v1/network/apply");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(JSON.parse(calls[1].init.body).mode, "lan-https");
});
