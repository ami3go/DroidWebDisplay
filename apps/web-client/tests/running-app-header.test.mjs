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

test("GUI task counter remains digits only", () => {
  assert.match(html, /id="running-app-count">0<\/span>/);
  assert.match(source, /count\.textContent = String\(this\.#apps\.length\)/);
});
