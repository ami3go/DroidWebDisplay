import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const css = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.css"), "utf8");

test("header override removes legacy pseudo logo and keeps brand on one row", () => {
  assert.match(css, /\.topbar-brand::before,[\s\S]*\.gb-rail::before/);
  assert.match(css, /content: none !important/);
  assert.match(css, /grid-template-columns: 54px minmax\(10\.6rem, auto\)/);
  assert.match(css, /grid-template-rows: 27px 27px/);
  assert.match(css, /\.topbar \{[\s\S]*flex-wrap: nowrap !important/);
  assert.match(css, /\.connection-row \{[\s\S]*flex-basis: auto !important/);
});

test("header override exposes independent phone and display states", () => {
  assert.match(css, /data-phone-found="true"[\s\S]*\.brand-phone/);
  assert.match(css, /data-connection-state="connecting"[\s\S]*\.brand-display/);
  assert.match(css, /data-connection-state="connected"[\s\S]*\.brand-display/);
  assert.match(css, /data-connection-state="connected"[\s\S]*> h1/);
  assert.match(css, /color: var\(--dwd-green\) !important/);
});

test("connection status is a plain subtitle rather than a pill", () => {
  assert.match(css, /\.topbar-brand > \.connection-status,[\s\S]*border: 0 !important/);
  assert.match(css, /border-radius: 0 !important/);
  assert.match(css, /background: transparent !important/);
  assert.match(css, /box-shadow: none !important/);
});
