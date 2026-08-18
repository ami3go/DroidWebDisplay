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

test("header override exposes independent phone and display states while keeping wordmark white", () => {
  assert.match(css, /data-phone-found="true"[\s\S]*\.brand-phone/);
  assert.match(css, /data-connection-state="connecting"[\s\S]*\.brand-display/);
  assert.match(css, /data-connection-state="connected"[\s\S]*\.brand-display/);
  assert.match(css, /\.topbar \.topbar-brand\[data-connection-state="connected"\] > h1 \{[\s\S]*color: #f2f7fc !important;[\s\S]*text-shadow: none !important;/);
  assert.match(css, /color: var\(--dwd-green\) !important/);
});

test("brand mark is smaller with a smaller phone and wider device spacing", () => {
  assert.match(css, /\.brand-device-status svg \{[\s\S]*width: 43px !important;[\s\S]*height: 43px !important;/);
  assert.match(css, /\.brand-phone \{[\s\S]*translate\(-1\.8px, 1\.2px\) scale\(\.80\)/);
  assert.match(css, /\.brand-display \{[\s\S]*translate\(1\.8px, \.4px\) scale\(\.91\)/);
  assert.match(css, /\.brand-device-link \{[\s\S]*scaleX\(1\.45\)/);
});

test("connection status is a plain subtitle rather than a pill", () => {
  assert.match(css, /\.topbar-brand > \.connection-status,[\s\S]*border: 0 !important/);
  assert.match(css, /border-radius: 0 !important/);
  assert.match(css, /background: transparent !important/);
  assert.match(css, /box-shadow: none !important/);
});
