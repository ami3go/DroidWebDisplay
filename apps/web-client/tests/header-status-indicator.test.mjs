import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const drawerSource = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.js"), "utf8");

test("header status icon animates connection transitions and recent actions", () => {
  assert.match(drawerSource, /function bindStatusActivityIndicator\(\)/);
  assert.match(drawerSource, /new MutationObserver/);
  assert.match(drawerSource, /attributeFilter: \['data-state'\]/);
  assert.match(drawerSource, /prefers-reduced-motion: reduce/);
  for (const action of ["navigation", "clipboard", "rotate", "resize", "power", "fullscreen", "apps", "warning"]) {
    assert.match(drawerSource, new RegExp(`${action}:`));
  }
  for (const control of ["back", "home", "recent", "power", "fullscreen", "running-app-icon"]) {
    assert.match(drawerSource, new RegExp(`${control.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}:`));
  }
  assert.match(drawerSource, /status-action-glyph/);
  assert.match(drawerSource, /bindStatusActivityIndicator\(\);/);
});
