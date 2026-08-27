import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import {
  MAX_QUICK_APP_BUTTONS,
  moveQuickApp,
  nextQuickAppPackage,
  normalizeQuickAppPackages,
  normalizeQuickAppsByDevice,
} from "../dist/assets/quick-apps.js";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const html = await readFile(resolve(root, "static/index.html"), "utf8");
const source = await readFile(resolve(root, "src/controller.ts"), "utf8");

const catalog = [
  { label: "ChatGPT", packageName: "com.openai.chatgpt", secondaryDisplayCompatibility: "supported" },
  { label: "Claude", packageName: "com.anthropic.claude", secondaryDisplayCompatibility: "unknown" },
  { label: "DeepSeek", packageName: "com.deepseek.chat", secondaryDisplayCompatibility: "unknown" },
];

test("quick application settings keep valid unique packages per Android device", () => {
  const manyPackages = Array.from({ length: MAX_QUICK_APP_BUTTONS + 4 }, (_, index) => `com.example.app${index}`);
  assert.deepEqual(
    normalizeQuickAppPackages([" com.openai.chatgpt ", "bad package", "com.openai.chatgpt", ...manyPackages]),
    ["com.openai.chatgpt", ...manyPackages.slice(0, MAX_QUICK_APP_BUTTONS - 1)],
  );
  assert.deepEqual(normalizeQuickAppsByDevice({
    phoneA: ["com.openai.chatgpt", "com.anthropic.claude"],
    phoneB: ["not-a-package", "com.deepseek.chat"],
    __proto__: ["com.invalid.prototype"],
  }), {
    phoneA: ["com.openai.chatgpt", "com.anthropic.claude"],
    phoneB: ["com.deepseek.chat"],
  });
});

test("add and reorder helpers preserve configured header order", () => {
  assert.equal(nextQuickAppPackage(["com.openai.chatgpt"], catalog), "com.anthropic.claude");
  assert.equal(nextQuickAppPackage(catalog.map((app) => app.packageName), catalog), null);
  assert.deepEqual(
    moveQuickApp(["com.openai.chatgpt", "com.anthropic.claude", "com.deepseek.chat"], 2, -1),
    ["com.openai.chatgpt", "com.deepseek.chat", "com.anthropic.claude"],
  );
  assert.deepEqual(moveQuickApp(["com.openai.chatgpt"], 0, -1), ["com.openai.chatgpt"]);
});

test("quick applications sit beside Android controls and are configurable in Settings", () => {
  const headerStart = html.indexOf('<header class="topbar">');
  const headerEnd = html.indexOf("</header>", headerStart);
  const header = html.slice(headerStart, headerEnd);
  assert.ok(header.indexOf('class="android-control-row"') < header.indexOf('id="quick-app-header"'));
  assert.ok(header.indexOf('id="quick-app-header"') < header.indexOf('class="running-app-header"'));
  for (const id of ["quick-app-add", "quick-app-list", "quick-app-settings-status"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(source, /quickApps: \{ byDevice: this\.#quickAppsByDevice \}/);
  assert.match(source, /normalizeQuickAppsByDevice\(quickApps\?\.byDevice\)/);
});

test("quick applications move running virtual tasks and use StartApp as the launch path", () => {
  assert.match(source, /await this\.#api\.runningApps\(server\.serial\)/);
  assert.match(source, /candidate\.packageName === packageName/);
  assert.match(source, /await this\.#api\.moveRunningApp\(\{/);
  assert.match(source, /await this\.sendMessages\(\[\{ type: ControlMessageType\.StartApp, name: packageName \}\]\)/);
  assert.match(source, /server\.displayMode === "virtual"/);
  assert.match(source, /"the phone screen \(display 0\)"/);
  assert.match(source, /Android was asked to open or bring/);
});
