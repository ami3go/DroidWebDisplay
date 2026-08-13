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
  assert.match(html, /id="running-app-icon" class="running-app-header-icon"/);
  assert.match(html, /id="running-app-count" class="running-app-count">0<\/span>/);
  assert.equal(html.includes('id="running-app-refresh"'), false);
  assert.match(source, /count\.textContent = String\(this\.#apps\.length\)/);
});

test("opening the app dropdown refreshes stale GUI tasks", () => {
  assert.match(source, /DROPDOWN_REFRESH_STALE_MS = 1500/);
  assert.match(source, /select\.addEventListener\("pointerdown", \(\) => void this\.refreshIfStale\(\)\)/);
  assert.match(source, /select\.addEventListener\("focus", \(\) => void this\.refreshIfStale\(\)\)/);
  assert.match(source, /Date\.now\(\) - this\.#lastRefreshAt < DROPDOWN_REFRESH_STALE_MS/);
});
