import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const drawerSource = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.js"), "utf8");
const connectCss = await readFile(resolve(root, "static/droidwebdisplay-connect-drawer.css"), "utf8");
const html = await readFile(resolve(root, "static/index.html"), "utf8");

test("Connect is the first drawer group and owns connection controls", () => {
  assert.match(drawerSource, /const GROUPS = \['connect','display'/);
  assert.match(drawerSource, /dataset\.group = 'connect'/);
  assert.match(drawerSource, /dataset\.slot = 'connect'/);
  for (const id of ["device", "refresh", "connect", "disconnect"]) {
    assert.match(drawerSource, new RegExp(`getElementById\\('${id}'\\)`));
  }
  assert.match(drawerSource, /actions\.append\(refresh, connect, disconnect\)/);
});

test("Connect controls use a compact non-overlapping three-column layout", () => {
  assert.match(drawerSource, /droidwebdisplay-connect-drawer\.css/);
  assert.match(connectCss, /grid-template-columns: repeat\(3, minmax\(0, 1fr\)\) !important/);
  assert.match(connectCss, /grid-column: auto !important/);
  assert.match(connectCss, /min-height: 2rem !important/);
  assert.match(connectCss, /#device[\s\S]*height: 2rem/);
  assert.match(connectCss, /@media \(max-width: 380px\)/);
});

test("readiness indicator stays in header and old subtitle is removed", () => {
  const start = html.indexOf('<header class="topbar">');
  const end = html.indexOf('</header>', start);
  const header = html.slice(start, end);
  assert.match(header, /id="connection-status"/);
  assert.match(header, /id="status-icon"/);
  assert.match(drawerSource, /LOCAL USB BRIDGE/);
  assert.match(drawerSource, /eyebrow\.remove\(\)/);
});