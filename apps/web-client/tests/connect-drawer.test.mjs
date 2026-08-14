import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const drawerSource = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.js"), "utf8");
const drawerCss = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.css"), "utf8");
const html = await readFile(resolve(root, "static/index.html"), "utf8");

test("Display is the first drawer group and owns connection controls", () => {
  assert.match(drawerSource, /const GROUPS = \['display','clipboard','files'/);
  assert.doesNotMatch(drawerSource, /data-group=\"connect\"/);
  assert.doesNotMatch(drawerSource, /dataset\.group = 'connect'/);
  const displayStart = html.indexOf('data-slot="display"');
  const audioStart = html.indexOf('data-slot="audio"', displayStart);
  const display = html.slice(displayStart, audioStart);
  assert.ok(displayStart >= 0);
  assert.match(display, /class="help-card connect-card"/);
  for (const id of ["device", "connect"]) {
    assert.match(display, new RegExp(`id="${id}"`));
  }
  assert.doesNotMatch(drawerSource, /ensureDisplayConnectionUi|actions\.append\(connect\)|displaySlot\.insertBefore/);
  assert.doesNotMatch(html, /id=\"refresh\"/);
});

test("Display connection controls use one compact stateful action", () => {
  assert.doesNotMatch(drawerSource, /droidwebdisplay-connect-drawer\.css/);
  assert.match(drawerCss, /data-slot=\"display\"/);
  assert.doesNotMatch(drawerCss, /data-slot=\"connect\"/);
  assert.match(drawerCss, /grid-template-columns: minmax\(0, 1fr\) !important/);
  assert.match(drawerCss, /grid-column: auto !important/);
  assert.match(drawerCss, /min-height: 2rem !important/);
  assert.match(drawerCss, /#device[\s\S]*height: 2rem/);
});

test("readiness indicator stays in header and Connect rail item is absent", () => {
  const start = html.indexOf('<header class="topbar">');
  const end = html.indexOf('</header>', start);
  const header = html.slice(start, end);
  assert.match(header, /id="connection-status"/);
  assert.match(header, /id="status-icon"/);
  assert.doesNotMatch(header, /id="device"/);
  assert.doesNotMatch(header, /id="connect"/);
  assert.doesNotMatch(drawerSource, /label\.textContent = 'Connect'/);
});

test("connection status pill opens Display settings", () => {
  assert.match(html, /id="connection-status"[^>]*role="button"[^>]*tabindex="0"/);
  assert.match(drawerSource, /function bindStatusShortcut\(\)/);
  assert.match(drawerSource, /status\.addEventListener\('click', openDisplay\)/);
  assert.match(drawerSource, /openGroup\('display'\)/);
});

test("Network settings are integrated into Access", () => {
  assert.doesNotMatch(html, /data-group="network"/);
  assert.doesNotMatch(html, /data-slot="network"/);
  assert.doesNotMatch(drawerSource, /'access','network'/);
  const accessStart = html.indexOf('data-slot="access"');
  const diagnosticsStart = html.indexOf('data-slot="diagnostics"', accessStart);
  const access = html.slice(accessStart, diagnosticsStart);
  assert.match(access, /data-section-key="access-network"/);
  assert.match(access, /id="network-card"/);
  assert.doesNotMatch(drawerSource, /mergeNetworkIntoAccess/);
});


test("drawer pin control is compact and close can unpin in one action", () => {
  assert.match(html, /class="gb-drawer-pin"[^>]*aria-label="Pin drawer"/);
  assert.doesNotMatch(html, /class="gb-pin-text"/);
  assert.match(drawerSource, /function closeOrUnpinDrawer\(\)/);
  assert.match(drawerSource, /if \(pinned\) applyPinned\(false\)/);
  assert.match(drawerSource, /Unpin and close drawer/);
  assert.match(drawerSource, /bindDrawerKeyboard\(\)/);
  assert.match(drawerSource, /event\.key !== 'Escape'/);
});

test("drawer width is user resizable and persisted", () => {
  assert.match(drawerSource, /DRAWER_WIDTH_KEY = 'droidwebdisplay\.ui\.drawer\.width\.v1'/);
  assert.match(drawerSource, /function bindDrawerResize\(\)/);
  assert.match(drawerSource, /gb-drawer-resize-handle/);
  assert.match(drawerSource, /addEventListener\('pointerdown'/);
  assert.match(drawerSource, /addEventListener\('pointermove'/);
  assert.match(drawerSource, /addEventListener\('dblclick'/);
  assert.match(drawerSource, /style\.setProperty\('--gb-drawer-w'/);
  assert.match(drawerCss, /\.gb-drawer-resize-handle \{/);
  assert.match(drawerCss, /cursor: ew-resize/);
});

test("File Explorer Name, Size and Modified columns resize independently", () => {
  assert.match(drawerSource, /EXPLORER_COLUMNS_KEY = 'droidwebdisplay\.ui\.explorer\.columns\.v2'/);
  assert.match(drawerSource, /name: \{ header: nameHeader, property: '--dwd-explorer-name-w'/);
  assert.match(drawerSource, /size: \{ header: sizeHeader, property: '--dwd-explorer-size-w'/);
  assert.match(drawerSource, /modified: \{ header: modifiedHeader, property: '--dwd-explorer-modified-w'/);
  assert.match(drawerSource, /addHandle\('name'\)/);
  assert.match(drawerSource, /addHandle\('size'\)/);
  assert.match(drawerSource, /addHandle\('modified'\)/);
  assert.match(drawerSource, /applyColumn\(key, startWidth \+ event\.clientX - startX\)/);
  assert.match(drawerSource, /resetColumn\(key\)/);
  assert.match(drawerCss, /--dwd-explorer-name-w, minmax\(80px, 1fr\)/);
  assert.match(drawerCss, /overflow-x: auto/);
});