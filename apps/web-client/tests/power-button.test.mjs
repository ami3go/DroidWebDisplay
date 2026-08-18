import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const index = fs.readFileSync(path.join(root, "static", "index.html"), "utf8");
const styles = fs.readFileSync(path.join(root, "static", "styles.css"), "utf8");
const controller = fs.readFileSync(path.join(root, "src", "controller.ts"), "utf8");

test("screen power button is a stateful phone icon", () => {
  assert.match(index, /id="power"[^>]*screen-power-button[^>]*data-screen-state="on"/);
  assert.match(index, /class="screen-power-phone"/);
  assert.match(index, /class="screen-power-display"/);
  assert.match(styles, /data-screen-state="on"[^}]*fill: #f3f6fb/s);
  assert.match(styles, /data-screen-state="off"[^}]*fill: #0a0d13/s);
  assert.match(controller, /this\.elements\.power\.dataset\.screenState = state/);
  assert.match(controller, /Turn Android screen off/);
  assert.match(controller, /Turn Android screen on/);
  assert.doesNotMatch(controller, /this\.elements\.power\.textContent = this\.#powerOn/);
});
