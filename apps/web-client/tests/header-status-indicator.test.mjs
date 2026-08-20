import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const drawerSource = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.js"), "utf8");
const drawerCss = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.css"), "utf8");


/** The object literal that follows `marker`, so an assertion about a map's keys
    cannot be satisfied by an unrelated identifier elsewhere in the file. */
function blockAfter(source, marker) {
  const start = source.indexOf(marker);
  assert.ok(start >= 0, `missing ${marker}`);
  const end = source.indexOf("};", start);
  assert.ok(end > start, `unterminated ${marker}`);
  return source.slice(start, end);
}

test("header status icon animates connection transitions and recent actions", () => {
  assert.match(drawerSource, /function bindStatusActivityIndicator\(\)/);
  assert.match(drawerSource, /new MutationObserver/);
  assert.match(drawerSource, /attributeFilter: \['data-state'\]/);
  assert.match(drawerSource, /prefers-reduced-motion: reduce/);
  // Scope to the maps under test. Searching the whole 600-line file made these
  // vacuous: `includes("back")` is satisfied by callback/fallback/background,
  // and a bare `${action}:` matches any object key anywhere in the file.
  const actionPaths = blockAfter(drawerSource, "const actionPaths = {");
  for (const action of ["navigation", "clipboard", "rotate", "resize", "power", "fullscreen", "apps", "warning"]) {
    assert.match(actionPaths, new RegExp(`(^|[\\s{,])['"\`]?${action}['"\`]?\\s*:`, "m"));
  }
  const controlActions = blockAfter(drawerSource, "const controlActions = {");
  for (const control of ["back", "home", "recent", "power", "fullscreen", "running-app-icon"]) {
    assert.match(controlActions, new RegExp(`(^|[\\s{,])['"\`]?${control}['"\`]?\\s*:`, "m"));
  }
  // running-app-select is bound separately, not through the controlActions map.
  assert.match(drawerSource, /getElementById\('running-app-select'\)\?\.addEventListener\('change'/);
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
