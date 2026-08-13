import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const drawerSource = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.js"), "utf8");
const connectCss = await readFile(resolve(root, "static/droidwebdisplay-connect-drawer.css"), "utf8");
const html = await readFile(resolve(root, "static/index.html"), "utf8");

test("Display is the first drawer group and owns connection controls", () => {
  assert.match(drawerSource, /const GROUPS = \['display','clipboard','files'/);
  assert.doesNotMatch(drawerSource, /data-group=\"connect\"/);
  assert.doesNotMatch(drawerSource, /dataset\.group = 'connect'/);
  assert.match(drawerSource, /data-slot=\"display\"/);
  for (const id of ["device", "connect"]) {
    assert.match(drawerSource, new RegExp(`getElementById\\('${id}'\\)`));
  }
  assert.match(drawerSource, /actions\.append\(connect\)/);
  assert.match(drawerSource, /displaySlot\.insertBefore\(card, displaySlot\.firstElementChild\)/);
  assert.doesNotMatch(html, /id=\"refresh\"/);
});

test("Display connection controls use one compact stateful action", () => {
  assert.match(drawerSource, /droidwebdisplay-connect-drawer\.css/);
  assert.match(connectCss, /data-slot=\"display\"/);
  assert.doesNotMatch(connectCss, /data-slot=\"connect\"/);
  assert.match(connectCss, /grid-template-columns: minmax\(0, 1fr\) !important/);
  assert.match(connectCss, /grid-column: auto !important/);
  assert.match(connectCss, /min-height: 2rem !important/);
  assert.match(connectCss, /#device[\s\S]*height: 2rem/);
});

test("readiness indicator stays in header and Connect rail item is absent", () => {
  const start = html.indexOf('<header class="topbar">');
  const end = html.indexOf('</header>', start);
  const header = html.slice(start, end);
  assert.match(header, /id="connection-status"/);
  assert.match(header, /id="status-icon"/);
  assert.doesNotMatch(drawerSource, /label\.textContent = 'Connect'/);
});
