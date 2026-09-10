import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import {
  decideAutoConnect,
  normalizeReconnectAttemptSelection,
  reconnectAttemptLimit,
  reconnectDelayMilliseconds,
} from "../dist/assets/auto-connect.js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const controllerSource = await readFile(resolve(root, "src/controller.ts"), "utf8");

const ready = {
  enabled: true,
  connected: false,
  connecting: false,
  selectedReadySerial: "phone-1",
  manualDisconnectSerial: null,
  blockedSerial: null,
};

test("auto-connect starts only for an enabled ready selected USB device", () => {
  assert.equal(decideAutoConnect(ready), "connect");
  assert.equal(decideAutoConnect({ ...ready, enabled: false }), "disabled");
  assert.equal(decideAutoConnect({ ...ready, selectedReadySerial: null }), "waiting-for-device");
  assert.equal(decideAutoConnect({ ...ready, connected: true }), "busy");
  assert.equal(decideAutoConnect({ ...ready, connecting: true }), "busy");
});

test("manual Disconnect pauses the same phone but allows a newly selected phone", () => {
  assert.equal(decideAutoConnect({ ...ready, manualDisconnectSerial: "phone-1" }), "paused-after-manual-disconnect");
  assert.equal(decideAutoConnect({ ...ready, manualDisconnectSerial: "phone-2" }), "connect");
});

test("retry exhaustion pauses a failing phone until it disappears or is manually retried", () => {
  assert.equal(decideAutoConnect({ ...ready, blockedSerial: "phone-1" }), "paused-after-failures");
  assert.equal(decideAutoConnect({ ...ready, blockedSerial: "phone-2" }), "connect");
});

test("retry choices support 10, 100 and unlimited with legacy migration", () => {
  assert.equal(normalizeReconnectAttemptSelection(10), "10");
  assert.equal(normalizeReconnectAttemptSelection("100"), "100");
  assert.equal(normalizeReconnectAttemptSelection("infinite"), "infinite");
  assert.equal(normalizeReconnectAttemptSelection("∞"), "infinite");
  assert.equal(normalizeReconnectAttemptSelection(5), "10");
  assert.equal(reconnectAttemptLimit("10"), 10);
  assert.equal(reconnectAttemptLimit("100"), 100);
  assert.equal(reconnectAttemptLimit("infinite"), null);
});

test("retry timeout grows progressively and caps at one minute", () => {
  assert.deepEqual(
    [0, 1, 2, 3, 4, 5, 99].map(reconnectDelayMilliseconds),
    [1_000, 2_000, 5_000, 10_000, 30_000, 60_000, 60_000],
  );
});

test("controller watches USB only when enabled and preserves deliberate Disconnect", () => {
  assert.match(controllerSource, /if \(this\.elements\.autoReconnect\.checked\) this\.scheduleUsbAutoConnect\(0\)/);
  assert.match(controllerSource, /this\.#manualDisconnectSerial = this\.#serverSession\?\.serial \?\? this\.selectedReadySerial\(\)/);
  assert.match(controllerSource, /!readySerials\.has\(this\.#manualDisconnectSerial\)/);
  assert.match(controllerSource, /if \(!this\.elements\.autoReconnect\.checked\) \{/);
  assert.match(controllerSource, /this\.cancelReconnect\(\)/);
  assert.match(controllerSource, /USB_AUTO_CONNECT_POLL_MS = 2000/);
});

test("primary Connect button refreshes device state and performs manual retry", () => {
  assert.match(controllerSource, /private async handleConnectButton\(\): Promise<void> \{[\s\S]*await this\.reconnectNow\(\);[\s\S]*\}/);
  assert.match(controllerSource, /private async reconnectNow\(\): Promise<void> \{[\s\S]*await this\.refreshDevices\(\);[\s\S]*await this\.refreshVirtualCapabilities\(\);[\s\S]*await this\.connectByUser\(\);/);
  assert.doesNotMatch(controllerSource, /elements\.reconnect\b/);
});
