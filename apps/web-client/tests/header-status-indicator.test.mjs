import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const drawerSource = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.js"), "utf8");
const drawerCss = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.css"), "utf8");

test("header status icon animates connection transitions and recent actions", () => {
  assert.match(drawerSource, /function bindStatusActivityIndicator\(\)/);
  assert.match(drawerSource, /new MutationObserver/);
  assert.match(drawerSource, /attributeFilter: \['data-state'\]/);
  assert.match(drawerSource, /prefers-reduced-motion: reduce/);
  for (const action of ["navigation", "clipboard", "rotate", "resize", "power", "fullscreen", "apps", "warning"]) {
    assert.match(drawerSource, new RegExp(`${action}:`));
  }
  for (const control of ["back", "home", "recent", "power", "fullscreen", "running-app-icon", "running-app-select"]) {
    assert.match(drawerSource, new RegExp(`['"\`]${control}['"\`]`));
  }
  assert.match(drawerSource, /status-action-glyph/);
  assert.match(drawerSource, /bindStatusActivityIndicator\(\);/);
});

test("brand phone and display SVG rendering is shipped in external CSS", () => {
  assert.match(drawerCss, /\.brand-phone-frame,[\s\S]*\.brand-display-frame,[\s\S]*fill: none !important;[\s\S]*stroke: currentColor !important;/);
  assert.match(drawerCss, /\.brand-phone-screen,[\s\S]*\.brand-display-screen[\s\S]*fill: #0a0d13 !important;[\s\S]*stroke: currentColor !important;/);
  assert.match(drawerCss, /\.brand-phone-home \{[\s\S]*fill: currentColor !important;/);
  assert.match(drawerCss, /data-phone-found="true"[\s\S]*\.brand-phone[\s\S]*var\(--dwd-green\)/);
  assert.match(drawerCss, /data-connection-state="connecting"[\s\S]*\.brand-display[\s\S]*brand-display-pulse/);
  assert.match(drawerCss, /data-connection-state="connected"[\s\S]*\.brand-display,[\s\S]*\.brand-device-link[\s\S]*var\(--dwd-green\)/);
});
