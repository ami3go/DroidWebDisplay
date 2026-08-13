import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const css = await readFile(resolve(root, "static/styles.css"), "utf8");
const html = await readFile(resolve(root, "static/index.html"), "utf8");
const mainSource = await readFile(resolve(root, "src/main.ts"), "utf8");
const controllerSource = await readFile(resolve(root, "src/controller.ts"), "utf8");
const runningAppSource = await readFile(resolve(root, "src/running-app-controller.ts"), "utf8");



test("workspace is the native single-stage production layout", () => {
  assert.match(html, /data-ui="droidwebdisplay-native-single-drawer-v1"/);
  assert.match(html, /class="workspace native-workspace"/);
  assert.equal(html.includes('<aside class="sidepanel">'), false);
  assert.equal(html.includes('<aside class="transfer-panel"'), false);
  assert.match(css, /\.native-workspace \{[\s\S]*grid-template-columns: minmax\(0, 1fr\) !important;/);
});

test("Display Mode controls are contained inside their card", () => {
  assert.match(css, /select \{ min-width: 0; max-width: 100%;/);
  assert.match(css, /\.display-mode-card > label,/);
  assert.match(css, /\.virtual-display-settings > label,/);
  assert.match(css, /\.display-mode-card select,[\s\S]*max-width: 100%;/);
  assert.match(css, /#restore-profile \{ white-space: normal; overflow-wrap: anywhere; \}/);
});

test("Display Mode numeric fields collapse safely on narrow viewports", () => {
  assert.match(css, /\.three-field-row > label:last-child \{ grid-column: 1 \/ -1; \}/);
  assert.match(css, /@media \(max-width: 520px\)[\s\S]*\.three-field-row, \.two-field-row \{ grid-template-columns: 1fr; \}/);
  assert.match(html, /id="virtual-width"/);
  assert.match(html, /id="virtual-height"/);
  assert.match(html, /id="virtual-dpi"/);
});

test("running applications panel is native to the Apps drawer", () => {
  const appsSlot = html.indexOf('data-slot="apps"');
  const filesSlot = html.indexOf('data-slot="files"');
  const panel = html.indexOf('id="running-app-select"');
  assert.ok(appsSlot >= 0 && panel > appsSlot && panel < filesSlot);
  assert.match(html, /id="running-app-move"/);
});

test("PIN gate and PC-local trust wording are present", () => {
  assert.match(html, /id="auth-gate"/);
  assert.match(html, /Only this browser session/);
  assert.match(html, /1 hour/);
  assert.match(html, /1 day/);
  assert.match(html, /1 week/);
  assert.match(html, /1 month/);
  assert.match(html, /1 year/);
  assert.match(html, /Forever, until revoked/);
  assert.match(html, /Custom duration/);
  assert.match(html, /The Android phone does not remember or authorize this browser/);
  assert.match(html, /id="auth-session-list"/);
  assert.match(html, /id="auth-revoke-all"/);
});


test("file controls use the accepted production labels", () => {
  for (const label of [">Load<", ">Browse<", ">Download<", ">Reset<"]) assert.match(html, new RegExp(label));
  for (const required of ["Destination folder", "File sync", "Transfer queue"]) assert.match(html, new RegExp(required));
  for (const old of ["Upload selected file(s)", "Automatic two-way folder sync", "PC destination", "data-gate4-check", "data-gate5-check", "data-gate6-check", "data-gate7-check"]) assert.equal(html.includes(old), false);
  assert.match(css, /\.uniform-buttons > button \{ min-height: 2\.55rem; height: 2\.55rem;/);
  assert.match(css, /#screen \{ cursor: default; \}/);
});

test("audio reconnect clipboard and settings controls are present without layout modes", () => {
  for (const id of ["audio-enabled", "audio-mute", "audio-volume", "auto-reconnect", "reconnect", "clipboard-auto-sync", "clipboard-max-kib", "clipboard-copy-android", "settings-export", "settings-import"]) assert.match(html, new RegExp(`id=\"${id}\"`));
  assert.equal(html.includes('id="workspace-layout"'), false);
  assert.equal(controllerSource.includes("workspaceLayout"), false);
  assert.match(css, /:focus-visible/);
});

test("native drawer uses persisted accordions only for multi-section groups", () => {
  assert.match(html, /id="gb-single-drawer-root"/);
  assert.match(html, /data-section-key="files-load"/);
  assert.match(html, /data-section-key="access-web-browser"/);
  assert.equal(mainSource.includes("initializeCollapsibleCards"), false);
  assert.equal(html.includes("card-collapse-button"), false);
});

test("Focus-style workspace is permanent and has no layout selector", () => {
  const headerStart = html.indexOf('<header class="topbar">');
  const headerEnd = html.indexOf('</header>', headerStart);
  const header = html.slice(headerStart, headerEnd);
  assert.match(header, /id="fullscreen"/);
  assert.equal(header.includes('id="workspace-layout"'), false);
  assert.equal(controllerSource.includes("applyWorkspaceLayout"), false);
  assert.equal(controllerSource.includes("workspaceLayout"), false);
});

test("audio card uses the concise label without the experimental badge", () => {
  assert.match(html, /<h2>Audio<\/h2>/);
  assert.equal(html.includes("Audio experimental"), false);
  assert.equal(html.includes("Experimental:"), false);
  assert.match(html, /Browser audio may have interruptions or delay/);
  assert.equal(css.includes(".experimental-badge"), false);
});

test("File sync controls are present", () => {
  for (const id of ["auto-download-enabled", "auto-upload-enabled", "auto-upload-duplicate", "auto-upload-existing"]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /File sync/);
  assert.equal(html.includes("Automatic two-way folder sync"), false);
  assert.match(html, /Files created by one sync direction are fingerprinted/);
});

test("connection status is a one-unit toolbar pill with state icons", () => {
  const headerStart = html.indexOf('<header class="topbar">');
  const headerEnd = html.indexOf('</header>', headerStart);
  const header = html.slice(headerStart, headerEnd);
  assert.match(header, /id="connection-status"/);
  assert.match(header, /id="status-icon"/);
  assert.match(header, /class="status-ring-progress"/);
  assert.match(header, /class="status-check"/);
  assert.equal(html.includes('class="status-card"'), false);
  assert.match(css, /\.connection-status \{[^}]*height: 2\.12rem;[^}]*display: inline-flex;/s);
  assert.match(css, /\.connection-status\[data-state="connected"\]/);
  assert.match(css, /\.connection-status\[data-state="disconnected"\]/);
  assert.match(css, /\.connection-status\[data-state="connecting"\]/);
  assert.match(css, /connection-ring-spin/);
  assert.match(css, /border-radius: 999px/);
  assert.match(mainSource, /statusContainer: required<HTMLElement>\("#connection-status"\)/);
});

test("compact header keeps device and Android controls beside the title", () => {
  const headerStart = html.indexOf('<header class="topbar">');
  const headerEnd = html.indexOf('</header>', headerStart);
  const header = html.slice(headerStart, headerEnd);
  for (const id of ["device", "refresh", "connect", "disconnect", "back", "home", "recent", "rotate", "power", "fullscreen"]) {
    assert.match(header, new RegExp(`id="${id}"`));
  }
  assert.match(header, /class="topbar-brand"/);
  assert.match(header, /class="android-control-row"/);
  assert.match(css, /\.topbar \{ display: flex; align-items: center;/);
  assert.match(css, /padding: 0\.52rem 0\.85rem/);
});

test("optional LAN access is explicit, authenticated and recoverable", () => {
  for (const id of [
    "network-card", "network-mode", "network-interface", "network-allowed-networks",
    "network-certificate-source", "network-manage-firewall", "network-current-pin",
    "network-validate", "network-apply", "network-disable", "network-download-certificate",
  ]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /Local PC only/);
  assert.match(html, /Private LAN with HTTPS/);
  assert.match(html, /HTTPS and PIN authentication are mandatory/);
  assert.match(html, /reset_network_access\.py --local-only/);
  assert.match(mainSource, /NetworkAccessController/);
  assert.match(css, /\.network-warning/);
  assert.match(css, /\.network-mode-badge\.lan-enabled/);
});


test("automatic clipboard sync never triggers Android paste", () => {
  assert.match(controllerSource, /pollPcClipboard[\s\S]*synchronizePcClipboard\(text, sessionId, session\)/);
  assert.match(controllerSource, /synchronizePcClipboard[\s\S]*clipboardMessage\(text, sequence, false\)/);
  assert.doesNotMatch(controllerSource, /pollPcClipboard[\s\S]{0,700}pasteText\(text/);
});


test("automatic clipboard polling never prompts from the background", () => {
  assert.match(controllerSource, /startClipboardPolling\(requestPermission: boolean\)/);
  assert.match(controllerSource, /permissionState !== "granted" && !requestPermission/);
  assert.match(controllerSource, /#clipboardReadAllowed/);
  assert.match(controllerSource, /Stop polling after the first runtime permission failure/);
});


test("virtual keyboard suppression is virtual-display-only and Ctrl+V is explicit", () => {
  assert.match(html, /id="virtual-hide-keyboard"/);
  assert.match(html, /Virtual display only\. Phone screen mode keeps the normal Android keyboard behavior\./);
  assert.match(controllerSource, /shortcut === "paste"[\s\S]*pasteClipboard\("Ctrl\+V"\)/);
  assert.match(controllerSource, /shortcut === "copy"[\s\S]*androidClipboardCopyMessage\(\)/);
  assert.match(controllerSource, /hideVirtualKeyboard\.checked \? "hide"/);
});


test("multi-display workspace exposes live accessible session tabs", () => {
  for (const id of ["display-tabs", "display-tab-add", "display-name", "stage-hint"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /role="tablist"/);
  assert.match(css, /\.display-tab\[data-active="true"\]/);
  assert.match(css, /\.display-canvas\[hidden\]/);
  assert.match(mainSource, /tabs: required<HTMLElement>\("#display-tabs"\)/);
  assert.match(controllerSource, /#runtimes = new Map<string, DisplayRuntime>\(\)/);
  assert.match(controllerSource, /activateRuntime\(sessionId: string\)/);
  assert.match(controllerSource, /cleanupRuntime\(sessionId: string\)/);
  assert.match(controllerSource, /value\.audioPlayer\.setMuted\(id === sessionId \? userMuted : true\)/);
  assert.match(controllerSource, /while \(this\.#runtimes\.get\(sessionId\)\?\.protocolSession === session\)/);
  assert.doesNotMatch(controllerSource, /if \(this\.#serverSession\) return;/);
});

test("tab input maps against the active runtime canvas", () => {
  assert.match(controllerSource, /canvas !== runtime\.canvas/);
  assert.match(controllerSource, /canvas\.getBoundingClientRect\(\)/);
  assert.match(controllerSource, /canvas\.setPointerCapture\(event\.pointerId\)/);
});


test("tab canvas cleanup never reacquires a transferred OffscreenCanvas context", () => {
  const start = controllerSource.indexOf("private releaseRuntimeCanvas");
  const end = controllerSource.indexOf("private bindCanvasEvents", start);
  const cleanup = controllerSource.slice(start, end);
  assert.ok(start >= 0 && end > start);
  assert.doesNotMatch(cleanup, /getContext/);
  assert.match(cleanup, /renderer\/worker code remains the sole owner/);
});

test("clipboard async fallbacks stay bound to the initiating display tab", () => {
  assert.match(controllerSource, /this\.#activeSessionId !== sessionId \|\| this\.#protocolSession !== session/);
  assert.match(controllerSource, /for \(const message of textInjectionMessages\(text\)\) await session\.sendControl\(message\)/);
  assert.doesNotMatch(controllerSource, /await this\.sendMessages\(textInjectionMessages\(text\)\)/);
  assert.match(controllerSource, /synchronizePcClipboard\(initial, sessionId, session\)/);
  assert.match(controllerSource, /synchronizePcClipboard\(text, sessionId, session\)/);
  assert.match(controllerSource, /this\.#copyShortcutPending = false;[\s\S]{0,400}const userMuted/);
});


test("Phase 5 enforces visible display capacity and per-display diagnostics", () => {
  assert.match(html, /id="display-tab-capacity"/);
  assert.match(html, /id="display-diagnostics"/);
  assert.match(mainSource, /tabCapacity: required<HTMLElement>\("#display-tab-capacity"\)/);
  assert.match(mainSource, /displayDiagnostics: required<HTMLElement>\("#display-diagnostics"\)/);
  assert.match(controllerSource, /#maximumDisplaySessions = 4/);
  assert.match(controllerSource, /#availableDisplaySlots = 4/);
  assert.match(controllerSource, /atCapacity = this\.#availableDisplaySlots <= 0/);
  assert.match(controllerSource, /renderDisplayDiagnostics/);
});

test("Phase 5 tab switching stays synchronous and browser-only with a 50 ms target", () => {
  assert.match(controllerSource, /const TAB_SWITCH_TARGET_MS = 50/);
  const start = controllerSource.indexOf("private activateRuntime");
  const end = controllerSource.indexOf("private bindControlDebug", start);
  assert.ok(start >= 0 && end > start);
  const body = controllerSource.slice(start, end);
  assert.doesNotMatch(body, /await\s/);
  assert.doesNotMatch(body, /#api/);
  assert.doesNotMatch(body, /startDeviceSession|recordApplicationLaunch|refreshDevices/);
  assert.match(body, /performance\.now\(\)/);
  assert.match(body, /audioPlayer\.setMuted/);
});

test("active-session event does not query ADB or REST during tab switch", () => {
  const start = runningAppSource.indexOf('globalThis.addEventListener("droidwebdisplay-active-session"');
  const end = runningAppSource.indexOf("  });", start);
  assert.ok(start >= 0 && end > start);
  const body = runningAppSource.slice(start, end);
  assert.doesNotMatch(body, /refresh\(/);
  assert.doesNotMatch(body, /#api/);
  assert.match(body, /selectActiveVirtualSession/);
});


test("clipboard polling cannot steal focus from an active Android display", () => {
  assert.match(controllerSource, /private activeDisplayOwnsKeyboardFocus\(\)/);
  assert.match(controllerSource, /runtime\?\.canvas === document\.activeElement/);
  const start = controllerSource.indexOf("private async startClipboardPolling");
  const end = controllerSource.indexOf("private stopClipboardPolling", start);
  const polling = controllerSource.slice(start, end);
  assert.match(polling, /permissionState === "granted" && !requestPermission && this\.activeDisplayOwnsKeyboardFocus\(\)/);
  assert.match(polling, /this\.activeDisplayOwnsKeyboardFocus\(\)/);
  assert.match(polling, /this\.#clipboardPollTimer = window\.setInterval/);
});

test("display diagnostics distinguish focus loss from control transport failure", () => {
  assert.match(controllerSource, /control focus \$\{runtime\.canvas === document\.activeElement \? "canvas" : "lost"\}/);
  assert.match(controllerSource, /canvas\.addEventListener\("focus", \(\) => \{[\s\S]{0,300}controlDebug\("focus", "canvas-focus"[\s\S]{0,300}renderDisplayDiagnostics\(true\)/);
  assert.match(controllerSource, /canvas\.addEventListener\("blur", \(\) => \{[\s\S]{0,500}controlDebug\("focus", "canvas-blur"[\s\S]{0,500}renderDisplayDiagnostics\(true\)/);
});


test("control debug logging is downloadable and instruments the full pointer path", async () => {
  const debugSource = await readFile(resolve(root, "src/control-debug.ts"), "utf8");
  const transportSource = await readFile(resolve(root, "src/websocket-transport.ts"), "utf8");
  for (const id of ["control-debug-summary", "control-debug-download", "control-debug-clear"]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(mainSource, /controlDebugDownload: required<HTMLButtonElement>\("#control-debug-download"\)/);
  assert.match(controllerSource, /controlDebug\("pointer", "event"/);
  assert.match(controllerSource, /controlDebug\("pointer", "send-complete"/);
  assert.match(controllerSource, /controlDebug\("pointer", "send-error"/);
  assert.match(controllerSource, /recordControlHeartbeat/);
  assert.match(controllerSource, /displayDiagnostics\(serial\)/);
  assert.match(transportSource, /controlDebug\("websocket", "opened"/);
  assert.match(transportSource, /controlDebug\("websocket", "closed"/);
  assert.match(transportSource, /controlDebug\("control-writer", "write"/);
  assert.match(debugSource, /MAX_CONTROL_DEBUG_EVENTS = 1500/);
  assert.match(debugSource, /clipboard\|pin\|password\|token\|cookie/);
  assert.doesNotMatch(controllerSource, /controlDebug\([^\n]*message\.text/);
});
