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
const transferSource = await readFile(resolve(root, "src/transfer-controller.ts"), "utf8");
const autoDownloadSource = await readFile(resolve(root, "src/auto-download-controller.ts"), "utf8");
const runningAppSource = await readFile(resolve(root, "src/running-app-controller.ts"), "utf8");
const drawerSource = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.js"), "utf8");
const drawerCssSource = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.css"), "utf8");



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
  assert.equal(html.includes('id=\"restore-profile\"'), false);
  assert.match(controllerSource, /displayProfile\.addEventListener\(\"change\"[\s\S]*applyProfile\(this\.elements\.displayProfile\.value\)/);
  assert.match(controllerSource, /onCustomDisplayChange\(\)[\s\S]*displayProfile\.value = \"custom\"/);
});

test("Display Mode numeric fields collapse safely on narrow viewports", () => {
  assert.match(css, /\.three-field-row > label:last-child \{ grid-column: 1 \/ -1; \}/);
  assert.match(css, /@media \(max-width: 520px\)[\s\S]*\.three-field-row, \.two-field-row \{ grid-template-columns: 1fr; \}/);
  assert.match(html, /id="virtual-width"/);
  assert.match(html, /id="virtual-height"/);
  assert.match(html, /id="virtual-dpi"/);
});

test("running applications are compact header controls with automatic relocation", () => {
  const headerStart = html.indexOf('<header class="topbar">');
  const headerEnd = html.indexOf('</header>', headerStart);
  const header = html.slice(headerStart, headerEnd);
  const fullscreen = header.indexOf('id="fullscreen"');
  const icon = header.indexOf('class="running-app-header-icon"');
  const select = header.indexOf('id="running-app-select"');
  assert.ok(fullscreen >= 0 && icon > fullscreen && select > icon);
  assert.match(header, /id="running-app-count" class="running-app-count">0<\/span>/);
  assert.equal(header.includes('id="running-app-refresh"'), false);
  assert.equal(html.includes('data-group="apps"'), false);
  assert.equal(html.includes('data-slot="apps"'), false);
  assert.equal(html.includes('id="running-app-move"'), false);
  assert.match(runningAppSource, /select\.addEventListener\("change", \(\) => void this\.handleSelectionChange\(\)\)/);
  assert.match(runningAppSource, /select\.addEventListener\("pointerdown", \(\) => this\.beginDropdownInteraction\(\)\)/);
  assert.match(runningAppSource, /select\.addEventListener\("focus", \(\) => this\.beginDropdownInteraction\(\)\)/);
  assert.match(runningAppSource, /count\.textContent = String\(this\.#apps\.length\)/);
  assert.match(css, /\.running-app-header \{ height: 2\.12rem; min-height: 2\.12rem;/);
  assert.match(css, /\.running-app-count \{ position: absolute;/);
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
  for (const label of [">Download<", ">Reset<"]) assert.match(html, new RegExp(label));
  for (const required of ["Android File Explorer", "Destination folder", "Custom PC folder", "File sync", "Transfer queue"]) assert.match(html, new RegExp(required));
  for (const old of [">Load<", ">Browse<", "Upload selected file(s)", "Automatic two-way folder sync", "PC destination", "data-gate4-check", "data-gate5-check", "data-gate6-check", "data-gate7-check"]) assert.equal(html.includes(old), false);
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
  assert.doesNotMatch(html, /data-section-key="files-load"/);
  assert.match(html, /data-section-key="files-explorer"/);
  assert.match(html, /data-section-key="files-sync"/);
  assert.match(html, /data-section-key="files-queue"/);
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

test("Android File Explorer delegates row interaction listeners", () => {
  assert.match(transferSource, /storageBody\.addEventListener\("click"/);
  assert.match(transferSource, /storageBody\.addEventListener\("dblclick"/);
  assert.match(transferSource, /storageBody\.addEventListener\("contextmenu"/);
  assert.match(transferSource, /storageBody\.addEventListener\("keydown"/);
  assert.match(transferSource, /row\.dataset\.index = String\(index\)/);
  assert.doesNotMatch(transferSource, /row\.addEventListener\(/);
  assert.doesNotMatch(transferSource, /selector\.addEventListener\(/);
  assert.doesNotMatch(transferSource, /menuButton\.addEventListener\(/);
});

test("Android File Explorer updates selection without rebuilding every row", () => {
  assert.match(transferSource, /private updateSelectionUi\(\): void/);
  assert.match(transferSource, /querySelectorAll<HTMLElement>\("\.explorer-row\[data-path\]"\)/);
  assert.match(transferSource, /row\.classList\.toggle\("selected", selected\)/);
});

test("mirrored screen is a drop target that uploads to the Android inbox", () => {
  // The Explorer drop zone lives inside the Files drawer, so using it means
  // navigating there first. The stage is where the user already is.
  assert.match(html, /id="stage-drop-overlay"/);
  assert.match(html, /Drop to send to Android/);
  assert.match(css, /\.stage \{ position: relative; \}/);
  assert.match(css, /\.stage-drop-overlay \{[\s\S]*pointer-events: none;/);

  for (const type of ["dragenter", "dragover", "dragleave", "drop"]) {
    assert.match(transferSource, new RegExp(`stage\\.addEventListener\\("${type}"`));
  }
  // Without preventDefault on dragover the browser navigates away to the file.
  assert.match(transferSource, /addEventListener\("dragover"[\s\S]*?event\.preventDefault\(\)/);
  // dragenter/dragleave fire per child element, so a depth counter is required
  // or the overlay flickers and sticks.
  assert.match(transferSource, /#stageDragDepth/);
  assert.match(transferSource, /uploadToInbox\(files\)/);
  // The server owns the default upload directory; the client must not restate it.
  assert.match(transferSource, /uploadFiles\(undefined, files\)/);
  assert.doesNotMatch(transferSource, /DroidWebDisplayInbox/);
});

test("Android File Explorer accepts PC file drag and drop", () => {
  assert.match(transferSource, /addEventListener\("dragover"/);
  assert.match(transferSource, /addEventListener\("drop"/);
  assert.match(transferSource, /uploadFiles\(destination, files\)/);
  assert.match(html, /Drag PC files onto a folder to upload there/);
});

test("device-dependent UI refreshes reject stale or overlapping results", () => {
  assert.match(controllerSource, /#capabilityRequestGeneration/);
  assert.match(transferSource, /#browseGeneration/);
  assert.match(transferSource, /#refreshTransfersBusy/);
  assert.match(autoDownloadSource, /#refreshing/);
  assert.match(runningAppSource, /#refreshQueued/);
});

test("Android File Explorer refreshes when stale", () => {
  assert.match(transferSource, /EXPLORER_REFRESH_STALE_MS = 3000/);
  assert.match(transferSource, /refreshExplorerIfStale/);
});

test("polling controllers stop cleanly and static asset versions advance", () => {
  assert.match(transferSource, /public close\(\): void/);
  assert.match(transferSource, /if \(this\.#closed\) return/);
  assert.match(autoDownloadSource, /public close\(\): void/);
  assert.match(mainSource, /transferController\.close\(\); autoDownloadController\.close\(\)/);
  assert.match(html, /main\.js\?v=0\.11\.2-native2/);
  assert.match(html, /droidwebdisplay-main-drawer\.css\?v=0\.11\.2-native5/);
  assert.match(html, /droidwebdisplay-main-drawer\.js\?v=0\.11\.2-native5/);
  assert.doesNotMatch(drawerCssSource, /data-group="apps"/);
});

test("idle file polling is adaptive and visibility aware", () => {
  assert.doesNotMatch(transferSource, /setInterval\(\(\) => void this\.refreshTransfers\(\), 750\)/);
  assert.match(transferSource, /transferRefreshDelay\(\)/);
  assert.match(transferSource, /document\.visibilityState !== "visible"/);
  assert.doesNotMatch(autoDownloadSource, /setInterval\(\(\) => void this\.refresh\(\), 1000\)/);
  assert.match(autoDownloadSource, /private refreshDelay\(\): number/);
  assert.match(autoDownloadSource, /monitoring \? 5000 : 10_000/);
});

test("File sync keeps Save primary and moves uncommon actions into overflow", () => {
  assert.match(html, /class="sync-action-row"/);
  assert.match(html, /class="sync-more-actions"/);
  assert.match(autoDownloadSource, /applySnapshot\(await this\.#api\.scanAutoDownload\(\)\)/);
});

test("File sync controls are present", () => {
  for (const id of ["auto-download-enabled", "auto-upload-enabled", "auto-upload-duplicate", "auto-upload-existing"]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /File sync/);
  assert.equal(html.includes("Automatic two-way folder sync"), false);
  assert.match(html, /Files created by one sync direction are fingerprinted/);
});

test("connection status is a state chip inside the brand lockup", () => {
  const headerStart = html.indexOf('<header class="topbar">');
  const headerEnd = html.indexOf('</header>', headerStart);
  const header = html.slice(headerStart, headerEnd);
  assert.match(header, /id="connection-status"/);
  assert.match(header, /id="status-icon"/);
  assert.match(header, /class="status-ring-progress"/);
  assert.match(header, /class="status-check"/);
  assert.equal(html.includes('class="status-card"'), false);
  // The chip sits under the wordmark, not beside it in the control row.
  const brand = header.slice(header.indexOf('class="topbar-brand"'), header.indexOf('class="connection-row"'));
  assert.match(brand, /<h1>DroidWebDisplay<\/h1>[\s\S]*id="connection-status"/);
  assert.equal(header.slice(header.indexOf('class="connection-row"')).includes('id="connection-status"'), false);
  assert.match(css, /\.topbar-brand \{[^}]*flex-direction: column;/s);
  assert.match(css, /\.connection-status \{[^}]*height: 1\.46rem;[^}]*display: inline-flex;/s);
  assert.match(css, /\.connection-status\[data-state="connected"\]/);
  assert.match(css, /\.connection-status\[data-state="disconnected"\]/);
  assert.match(css, /\.connection-status\[data-state="connecting"\]/);
  assert.match(css, /connection-ring-spin/);
  assert.match(css, /border-radius: 999px/);
  assert.match(mainSource, /statusContainer: required<HTMLElement>\("#connection-status"\)/);
});

test("compact header keeps Android controls while connection controls live directly in Display", () => {
  const headerStart = html.indexOf('<header class="topbar">');
  const headerEnd = html.indexOf('</header>', headerStart);
  const header = html.slice(headerStart, headerEnd);
  for (const id of ["back", "home", "recent", "rotate", "power", "fullscreen"]) {
    assert.match(header, new RegExp(`id="${id}"`));
  }
  assert.equal(header.includes('id="device"'), false);
  assert.equal(header.includes('id="connect"'), false);
  const displayStart = html.indexOf('data-slot="display"');
  const audioStart = html.indexOf('data-slot="audio"', displayStart);
  const display = html.slice(displayStart, audioStart);
  assert.match(display, /id="device"/);
  assert.match(display, /id="connect"/);
  assert.match(header, /class="topbar-brand"/);
  assert.match(header, /class="android-control-row"/);
  assert.match(css, /\.topbar \{ display: flex; align-items: center;/);
  assert.match(controllerSource, /DEVICE_DROPDOWN_REFRESH_STALE_MS/);
  assert.match(controllerSource, /device\.addEventListener\("pointerdown"/);
  assert.equal(html.includes('id="refresh"'), false);
  assert.equal(html.includes('id="disconnect"'), false);
  assert.match(controllerSource, /connect\.textContent = connected \? "Disconnect" : "Connect"/);
});

test("single drawer ships final structure without legacy runtime migration", () => {
  assert.equal(html.includes('data-slot="network"'), false);
  const accessStart = html.indexOf('data-slot="access"');
  const diagnosticsStart = html.indexOf('data-slot="diagnostics"', accessStart);
  const access = html.slice(accessStart, diagnosticsStart);
  assert.match(access, /data-section-key="access-network"/);
  assert.match(access, /id="network-card"/);
  assert.doesNotMatch(drawerSource, /ensureConnectionStyles|ensureDisplayConnectionUi|mergeNetworkIntoAccess|applyRailOrder|removeLegacyHeaderText/);
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


test("Clipboard drawer supports focused Ctrl+Enter Type", () => {
  assert.match(controllerSource, /clipboardText\.addEventListener\("keydown"/);
  assert.match(controllerSource, /event\.key === "Enter"[\s\S]*pasteTypedText\(\)/);
  assert.match(controllerSource, /updateClipboardUi/);
  assert.match(html, /id="clipboard-card"/);
});

test("automatic clipboard sync never triggers Android paste", () => {
  assert.match(controllerSource, /pollPcClipboard[\s\S]*synchronizePcClipboard\(text\)/);
  assert.match(controllerSource, /synchronizePcClipboard[\s\S]*clipboardMessage\(text, sequence, false\)/);
  assert.doesNotMatch(controllerSource, /pollPcClipboard[\s\S]{0,700}pasteText\(text/);
});


test("automatic clipboard polling never prompts from the background", () => {
  assert.match(controllerSource, /startClipboardPolling\(requestPermission: boolean\)/);
  assert.match(controllerSource, /if \(requestPermission\)/);
  assert.match(controllerSource, /permissionState !== "granted"/);
  assert.match(controllerSource, /#clipboardReadAllowed/);
  assert.match(controllerSource, /Stop polling after the first runtime permission failure/);
});


test("virtual keyboard suppression is virtual-display-only and Ctrl+V is explicit", () => {
  assert.match(html, /id="virtual-hide-keyboard"/);
  assert.match(html, /Virtual display only\. Phone screen mode keeps the normal Android keyboard behavior\./);
  assert.match(controllerSource, /shortcut === "copy"[\s\S]*androidClipboardCopyMessage\(\)/);
  assert.match(controllerSource, /hideVirtualKeyboard\.checked \? "hide"/);
});

test("Ctrl+V routes through a document paste listener, not a keydown shortcut", () => {
  // The paste event fires on the focused element, and the app moves focus off
  // the canvas (opening the clipboard panel focuses the fallback textarea), so
  // a canvas-scoped listener would make Ctrl+V silently dead. Binding on the
  // document is the behaviour under test.
  assert.match(controllerSource, /document\.addEventListener\("paste"[\s\S]*?pasteText\(text, "Ctrl\+V"\)/);
  assert.doesNotMatch(controllerSource, /canvas\.addEventListener\("paste"/);
  // Typing into the page's own text fields must still paste normally.
  assert.match(controllerSource, /isEditableTarget\(event\.target\)/);
  // clipboardShortcut must never claim Ctrl+V, or both paths would fire.
  assert.doesNotMatch(controllerSource, /shortcut === "paste"/);
});

test("Android File Explorer prioritizes destination then storage navigation", () => {
  const destination = html.indexOf('id="destination-profile"');
  const download = html.indexOf('id="download-selected"');
  const pcFolder = html.indexOf('id="open-pc-folder"');
  const storage = html.indexOf('id="storage-root"');
  const path = html.indexOf('id="storage-path"');
  const up = html.indexOf('id="storage-up"');
  const breadcrumbs = html.indexOf('id="storage-breadcrumbs"');
  const refresh = html.indexOf('id="storage-refresh"');
  const table = html.indexOf('class="explorer-frame"');
  assert.ok(destination < download && download < pcFolder);
  assert.ok(pcFolder < storage && storage < path);
  assert.ok(path < up && up < breadcrumbs && breadcrumbs < refresh);
  assert.ok(refresh < table);
});


test("Files drawer uses Explorer-only transfers with custom PC destination", () => {
  assert.doesNotMatch(html, /data-section-key="files-load"/);
  assert.doesNotMatch(html, /id="upload-file-button"/);
  assert.match(html, /id="context-upload-file"/);
  assert.match(html, /id="custom-destination-path"/);
  assert.match(html, /Custom PC folder/);
  assert.match(html, /id="duplicate-policy"/);
  assert.match(transferSource, /destinationPath/);
});

test("re-locking re-reads whether a PIN exists instead of reusing the setup form", async () => {
  const auth = await readFile(resolve(root, "src/auth-controller.ts"), "utf8");
  // The gate renders two different forms: setup (Confirm PIN visible) and
  // unlock. Only unhiding it on droidwebdisplay-auth-required left the setup
  // form on screen after a lock later in the same page session.
  assert.match(auth, /addEventListener\("droidwebdisplay-auth-required".*#reopenGate\(\)/);
  const reopen = auth.slice(auth.indexOf("async #reopenGate"), auth.indexOf("#renderGate(configured: boolean)"));
  assert.match(reopen, /await this\.#api\.authStatus\(\)/);
  assert.match(reopen, /this\.#renderGate\(configured\)/);
  // A burst of 401s must not clear the PIN box under someone mid-typing.
  assert.match(reopen, /if \(!this\.elements\.gate\.hidden \|\| this\.#reopening\) return;/);
  // The listener must not simply unhide the gate any more.
  assert.doesNotMatch(auth, /"droidwebdisplay-auth-required", \(\) => \{\s*this\.elements\.gate\.hidden = false;/);
});
