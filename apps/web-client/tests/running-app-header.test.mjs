import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const html = await readFile(resolve(root, "static/index.html"), "utf8");
const source = await readFile(resolve(root, "src/running-app-controller.ts"), "utf8");
const types = await readFile(resolve(root, "src/types.ts"), "utf8");

test("Diagnostics expose active display and available Android RAM", () => {
  assert.match(html, /id="diagnostic-display">—<\/strong>/);
  assert.match(html, /id="diagnostic-ram">—<\/strong>/);
  assert.match(source, /diagnosticDisplay\.textContent/);
  assert.match(source, /diagnosticRam\.textContent/);
  assert.match(types, /readonly freeMemoryBytes: number \| null;/);
});

test("GUI task counter is a digits-only badge on the app icon", () => {
  assert.match(html, /<button id="running-app-icon" class="running-app-header-icon"/);
  assert.match(html, /id="running-app-count" class="running-app-count">0<\/span>/);
  assert.equal(html.includes('id="running-app-refresh"'), false);
  assert.match(source, /count\.textContent = String\(this\.#apps\.length\)/);
});

test("dropdown refresh never rebuilds options during native selection", () => {
  assert.match(source, /DROPDOWN_REFRESH_STALE_MS = 1500/);
  assert.match(source, /select\.addEventListener\("pointerdown", \(\) => this\.beginDropdownInteraction\(\)\)/);
  assert.match(source, /select\.addEventListener\("blur", \(\) => void this\.finishDropdownInteraction\(\)\)/);
  assert.match(source, /if \(silent && this\.#dropdownActive\)/);
  assert.match(source, /this\.#refreshAfterDropdown = true/);
});

test("running app selector resets after each move action", () => {
  assert.match(source, /select\.addEventListener\("change", \(\) => void this\.handleSelectionChange\(\)\)/);
  assert.match(source, /this\.#elements\.select\.value = ""/);
  assert.match(source, /await this\.finishDropdownInteraction\(\)/);
});


test("app icon explicitly refreshes the running GUI task list", () => {
  assert.match(source, /elements\.icon\.addEventListener\("click"/);
  assert.match(source, /void this\.refresh\(\)/);
  assert.match(source, /Refresh running applications/);
});

test("every application selection calls the move API", () => {
  assert.doesNotMatch(source, /if \(app\.displayId === displayId\)/);
  assert.match(source, /await this\.#api\.moveRunningApp\(\{/);
});
