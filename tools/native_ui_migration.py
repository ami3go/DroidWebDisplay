#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web-client"
STATIC = WEB / "static"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def card(html: str, marker: str, closing: str = "</section>") -> str:
    start = html.index(marker)
    end = html.index(closing, start) + len(closing)
    return html[start:end]


def inner(section: str) -> str:
    return section[section.index(">") + 1:section.rfind("</section>")].strip()


def strip_first_h2(text: str) -> str:
    return re.sub(r"\s*<h2>.*?</h2>\s*", "\n", text, count=1, flags=re.S)


def accordion(key: str, title: str, content: str, open_by_default: bool = False) -> str:
    opened = " open" if open_by_default else ""
    return f'''<details class="gb-accordion" data-section-key="{key}"{opened}>
  <summary class="gb-accordion-summary"><span class="gb-accordion-triangle" aria-hidden="true">▸</span><span class="gb-accordion-label">{title}</span></summary>
  <div class="gb-accordion-content">{content}</div>
</details>'''


def rail_button(group: str, label: str) -> str:
    return f'<button type="button" class="gb-rail-button" data-group="{group}" aria-selected="false" title="{label}"><span class="gb-rail-icon" aria-hidden="true"></span><span class="gb-rail-label">{label}</span></button>'


def migrate_html() -> None:
    path = STATIC / "index.html"
    html = read(path)
    display = card(html, '<section class="help-card display-mode-card">')
    audio = card(html, '<section class="help-card phase9-session-card"')
    network = card(html, '<section id="network-card"')
    apps = card(html, '<section class="help-card running-app-card"')
    settings = card(html, '<section class="help-card settings-card">')
    diagnostics = card(html, '<section class="help-card statistics-card">')
    clipboard = card(html, '<div class="help-card clipboard-card">', "</div>")
    upload = card(html, '<section class="help-card transfer-section">')
    explorer = card(html, '<section class="help-card transfer-section storage-browser">')
    sync = card(html, '<section class="help-card transfer-section auto-download-card">')
    queue_start = html.index('<section class="help-card transfer-section">', html.index(sync) + len(sync))
    queue_end = html.index('</section>', queue_start) + len('</section>')
    queue = html[queue_start:queue_end]
    context_menu = card(html, '<div id="storage-context-menu"', "</div>")

    upload = upload.replace('<h2>Upload to Android</h2>', '<h2>Load</h2>').replace('>Upload</button>', '>Load</button>').replace('Android destination', 'Android destination folder')
    explorer = explorer.replace('PC destination', 'Destination folder')
    sync = sync.replace('Automatic two-way folder sync', 'File sync')
    diagnostics = diagnostics.replace('<h2>Statistics</h2>', '<h2>Mode statistic</h2>')
    settings = settings.replace('display, audio, clipboard, reconnect and layout preferences', 'display, audio, clipboard, reconnect and interface preferences')

    access = '''<section id="security-card" class="help-card security-card" hidden aria-label="Access settings">
  <details class="gb-accordion" data-section-key="access-web-browser" open>
    <summary class="gb-accordion-summary"><span class="gb-accordion-triangle" aria-hidden="true">▸</span><span class="gb-accordion-label">Web browser</span></summary>
    <div class="gb-accordion-content">
      <div class="section-heading"><h2>Web browser</h2><button id="auth-refresh-sessions" type="button" class="secondary compact">Refresh</button></div>
      <p id="auth-session-summary">Authenticated session</p>
      <p class="auth-trust-note">Trusted sessions belong to this DroidWebDisplay service and are not stored or approved by the Android phone.</p>
      <div id="auth-session-list" class="trusted-session-list"></div>
      <button id="auth-logout" type="button" class="secondary">Forget this browser</button>
    </div>
  </details>
  <details class="gb-accordion" data-section-key="access-pin">
    <summary class="gb-accordion-summary"><span class="gb-accordion-triangle" aria-hidden="true">▸</span><span class="gb-accordion-label">Pin</span></summary>
    <div class="gb-accordion-content security-form">
      <label>Current PIN<input id="auth-current-pin" type="password" inputmode="numeric" maxlength="12"></label>
      <label>New PIN<input id="auth-new-pin" type="password" inputmode="numeric" maxlength="12"></label>
      <label>Confirm new PIN<input id="auth-confirm-new-pin" type="password" inputmode="numeric" maxlength="12"></label>
      <button id="auth-change-pin" type="button">Change PIN and revoke all sessions</button>
    </div>
  </details>
  <details class="gb-accordion" data-section-key="access-revoke-all">
    <summary class="gb-accordion-summary"><span class="gb-accordion-triangle" aria-hidden="true">▸</span><span class="gb-accordion-label">Revoke all trusted sessions</span></summary>
    <div class="gb-accordion-content security-form">
      <label>Current PIN<input id="auth-revoke-all-pin" type="password" inputmode="numeric" maxlength="12"></label>
      <button id="auth-revoke-all" type="button" class="danger">Revoke all sessions</button>
    </div>
  </details>
  <p id="auth-security-status" class="running-app-status">Session protection active.</p>
</section>'''

    header_start = html.index('<header class="topbar">')
    header_end = html.index('</header>', header_start) + len('</header>')
    header = html[header_start:header_end]
    header = re.sub(r'\s*<label class="toolbar-layout-control">.*?</label>', '', header, flags=re.S)
    stage_start = html.index('<section id="stage"')
    stage_end = html.index('</section>', stage_start) + len('</section>')
    stage = html[stage_start:stage_end]

    files_content = "\n".join([
        accordion("files-load", "Load", strip_first_h2(inner(upload)), True),
        accordion("files-explorer", "Android File Explorer", strip_first_h2(inner(explorer)), True),
        context_menu,
        accordion("files-sync", "File sync", strip_first_h2(inner(sync))),
        accordion("files-queue", "Transfer queue", strip_first_h2(inner(queue))),
    ])
    groups = [
        ("apps", "Apps", apps), ("files", "Files", files_content), ("clipboard", "Clipboard", clipboard),
        ("display", "Display", display), ("audio", "Audio", audio), ("access", "Access", access),
        ("network", "Network", network), ("diagnostics", "Diagnostics", diagnostics), ("settings", "Settings", settings),
    ]
    rail = "\n        ".join(rail_button(g, label) for g, label, _ in groups)
    slots = "\n".join(f'          <div class="gb-drawer-slot" data-slot="{g}">{content}</div>' for g, _, content in groups)

    auth_start = html.index('<section id="auth-gate"')
    app_start = html.index('<main id="app"')
    prefix = html[:auth_start]
    auth = html[auth_start:app_start]
    prefix = prefix.replace('<html lang="en">', '<html lang="en" class="gb-single-drawer-enabled">')
    prefix = prefix.replace('<meta name="color-scheme" content="dark">', '<meta name="color-scheme" content="dark">\n  <meta http-equiv="Cache-Control" content="no-store, max-age=0">')
    prefix = prefix.replace('href="./droidwebdisplay-main-drawer.css"', 'href="./droidwebdisplay-main-drawer.css?v=0.11.2-native1"')

    native = f'''{prefix}{auth}<main id="app" class="shell" hidden data-ui="droidwebdisplay-native-single-drawer-v1">
    {header}
    <div id="gb-single-drawer-root" data-version="1.1.0">
      <nav class="gb-rail" aria-label="DroidWebDisplay tools">
        {rail}
        <div class="gb-rail-spacer"></div>
      </nav>
      <aside class="gb-drawer" aria-hidden="true">
        <div class="gb-drawer-header">
          <div class="gb-drawer-title">Tools</div>
          <button type="button" class="gb-drawer-pin" data-action="pin" aria-pressed="false" title="Pin drawer"><span aria-hidden="true">📌</span><span class="gb-pin-text">Pin</span></button>
          <button type="button" class="gb-drawer-close" aria-label="Close drawer" title="Close drawer">×</button>
        </div>
        <div class="gb-drawer-body">
{slots}
        </div>
        <div class="gb-drawer-footer"><button type="button" class="gb-drawer-action" data-action="close">Close</button></div>
      </aside>
    </div>
    <section class="workspace native-workspace">{stage}</section>
  </main>
  <script type="module" src="/assets/main.js?v=0.11.2-native1"></script>
  <script defer src="./droidwebdisplay-main-drawer.js?v=0.11.2-native1"></script>
</body>
</html>
'''
    for token in ('id="workspace-layout"', '<aside class="sidepanel">', '<aside class="transfer-panel"'):
        if token in native:
            raise RuntimeError(f"Legacy layout markup survived: {token}")
    write(path, native)


def migrate_drawer_js() -> None:
    write(STATIC / "droidwebdisplay-main-drawer.js", r'''/* DroidWebDisplay native single-drawer controller v1.1.0 */
(() => {
  'use strict';
  const PIN_KEY = 'droidwebdisplay.ui.drawer.pinned.v1';
  const LAST_GROUP_KEY = 'droidwebdisplay.ui.drawer.lastGroup.v1';
  const ACCORDION_KEY = 'droidwebdisplay.ui.drawer.accordions.v1';
  const ROOT_ID = 'gb-single-drawer-root';
  const GROUPS = ['apps','files','clipboard','display','audio','access','network','diagnostics','settings'];
  let activeGroup = null;
  let pinned = false;
  const root = () => document.getElementById(ROOT_ID);
  const drawer = () => root()?.querySelector('.gb-drawer');
  function get(key, fallback = null) { try { return localStorage.getItem(key) ?? fallback; } catch (_) { return fallback; } }
  function set(key, value) { try { localStorage.setItem(key, value); } catch (_) {} }
  function storedPinned() { return get(PIN_KEY, '0') === '1'; }
  function storedGroup() { const value = get(LAST_GROUP_KEY, 'display'); return GROUPS.includes(value) ? value : 'display'; }
  function applyPinned(value, persist = true) {
    pinned = Boolean(value);
    document.documentElement.classList.toggle('gb-single-drawer-pinned', pinned);
    root()?.classList.toggle('gb-pinned', pinned);
    const button = root()?.querySelector('.gb-drawer-pin');
    if (button) {
      button.setAttribute('aria-pressed', pinned ? 'true' : 'false');
      button.title = pinned ? 'Unpin drawer' : 'Pin drawer';
      const text = button.querySelector('.gb-pin-text'); if (text) text.textContent = pinned ? 'Pinned' : 'Pin';
    }
    if (persist) set(PIN_KEY, pinned ? '1' : '0');
    if (pinned) openGroup(activeGroup || storedGroup());
  }
  function openGroup(group) {
    if (!GROUPS.includes(group) || !root()) return;
    activeGroup = group; set(LAST_GROUP_KEY, group);
    root().querySelectorAll('.gb-drawer-slot').forEach(slot => slot.classList.toggle('gb-active', slot.dataset.slot === group));
    root().querySelectorAll('[data-group]').forEach(button => button.setAttribute('aria-selected', button.dataset.group === group ? 'true' : 'false'));
    const label = root().querySelector(`[data-group="${group}"] .gb-rail-label`)?.textContent || 'Tools';
    const title = root().querySelector('.gb-drawer-title'); if (title) title.textContent = label;
    drawer()?.classList.add('gb-open'); drawer()?.setAttribute('aria-hidden', 'false');
  }
  function closeDrawer() {
    if (pinned || !root()) return;
    drawer()?.classList.remove('gb-open'); drawer()?.setAttribute('aria-hidden', 'true');
    root().querySelectorAll('[data-group]').forEach(button => button.setAttribute('aria-selected', 'false'));
    activeGroup = null;
  }
  function loadAccordionState() { try { return JSON.parse(get(ACCORDION_KEY, '{}')) || {}; } catch (_) { return {}; } }
  function bindAccordions() {
    const state = loadAccordionState();
    root()?.querySelectorAll('details.gb-accordion[data-section-key]').forEach(details => {
      const key = details.dataset.sectionKey;
      if (Object.prototype.hasOwnProperty.call(state, key)) details.open = Boolean(state[key]);
      details.addEventListener('toggle', () => { const current = loadAccordionState(); current[key] = details.open; set(ACCORDION_KEY, JSON.stringify(current)); });
    });
  }
  function boot() {
    const ui = root(); if (!ui) return;
    document.documentElement.classList.add('gb-single-drawer-enabled');
    ui.querySelectorAll('[data-group]').forEach(button => button.addEventListener('click', () => openGroup(button.dataset.group)));
    ui.querySelector('.gb-drawer-pin')?.addEventListener('click', () => applyPinned(!pinned));
    ui.querySelectorAll('[data-action="close"], .gb-drawer-close').forEach(button => button.addEventListener('click', closeDrawer));
    bindAccordions(); applyPinned(storedPinned(), false); if (pinned) openGroup(storedGroup());
  }
  window.DroidWebDisplayDrawer = { openGroup, closeDrawer, setPinned: value => applyPinned(Boolean(value)) };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
})();
''')


def migrate_controller() -> None:
    path = WEB / "src" / "controller.ts"
    text = read(path)
    text = text.replace('  readonly workspaceLayout: HTMLSelectElement;\n', '')
    text = text.replace('    this.elements.workspaceLayout.addEventListener("change", () => this.applyWorkspaceLayout());\n', '')
    text = text.replace('localStorage.getItem("gptBridgeVirtualProfile")', 'localStorage.getItem("droidwebdisplay-virtual-profile-v1")')
    text = text.replace('localStorage.setItem("gptBridgeVirtualProfile", profile.profileId);', 'localStorage.setItem("droidwebdisplay-virtual-profile-v1", profile.profileId);')
    text = text.replace('Experimental Android audio capture is unavailable.', 'Android audio capture is unavailable.')
    text = re.sub(r'\n  private applyWorkspaceLayout\(\): void \{.*?\n  \}\n', '\n', text, count=1, flags=re.S)
    text = text.replace('      layout: this.elements.workspaceLayout.value,\n', '')
    text = re.sub(r'\n    this\.elements\.workspaceLayout\.value = .*?;\n    this\.applyWorkspaceLayout\(\);', '', text, count=1)
    if 'workspaceLayout' in text or 'gptBridgeVirtualProfile' in text:
        raise RuntimeError('Legacy workspace/profile state survived controller migration')
    write(path, text)


def migrate_main() -> None:
    path = WEB / "src" / "main.ts"
    text = read(path)
    text = re.sub(r'\nfunction initializeCollapsibleCards\(\): void \{.*?\n\}\n\nasync function bootstrap', '\nasync function bootstrap', text, count=1, flags=re.S)
    text = text.replace('    initializeCollapsibleCards();\n', '')
    text = text.replace('      workspaceLayout: required<HTMLSelectElement>("#workspace-layout"),\n', '')
    if 'initializeCollapsibleCards' in text or '#workspace-layout' in text:
        raise RuntimeError('Legacy card/layout initialization survived main.ts migration')
    write(path, text)


def migrate_css() -> None:
    path = STATIC / "styles.css"
    css = read(path)
    css += r'''

/* DroidWebDisplay native single-drawer production layout */
.native-workspace { grid-template-columns: minmax(0, 1fr) !important; align-items: stretch !important; gap: 0 !important; min-height: calc(100vh - 54px); padding: 0.75rem !important; }
.native-workspace > .stage { width: 100%; min-height: calc(100vh - 78px); }
#gb-single-drawer-root .help-card { margin: 0; }
#gb-single-drawer-root .gb-drawer-slot > .help-card + .help-card { margin-top: 8px; }
#gb-single-drawer-root .gb-accordion-content > .help-card { border: 0 !important; border-radius: 0 !important; background: transparent !important; box-shadow: none !important; padding: 0 !important; }
#gb-single-drawer-root .clipboard-actions { grid-template-columns: repeat(3, minmax(0, 1fr)); }
#gb-single-drawer-root .clipboard-actions button { min-width: 0; }
#gb-single-drawer-root .security-card { display: grid; gap: 8px; }
#gb-single-drawer-root .security-card[hidden], #gb-single-drawer-root .network-access-card[hidden] { display: none !important; }
@media (max-width: 700px) { .native-workspace { padding: 0.5rem !important; } .native-workspace > .stage { min-height: calc(100vh - 72px); } }
'''
    write(path, css)


def replace_test(source: str, name: str, block: str) -> str:
    marker = f'test("{name}"'
    start = source.find(marker)
    if start < 0:
        raise RuntimeError(f"Missing test block: {name}")
    next_start = source.find('\ntest("', start + len(marker))
    if next_start < 0:
        next_start = len(source)
    return source[:start] + block.rstrip() + '\n\n' + source[next_start:].lstrip('\n')


def migrate_layout_tests() -> None:
    path = WEB / "tests" / "layout.test.mjs"
    text = read(path)
    text = replace_test(text, "workspace uses one page-level vertical scrollbar", '''test("workspace is the native single-stage production layout", () => {\n  assert.match(html, /data-ui="droidwebdisplay-native-single-drawer-v1"/);\n  assert.match(html, /class="workspace native-workspace"/);\n  assert.equal(html.includes('<aside class="sidepanel">'), false);\n  assert.equal(html.includes('<aside class="transfer-panel"'), false);\n  assert.match(css, /\\.native-workspace \\{[\\s\\S]*grid-template-columns: minmax\\(0, 1fr\\) !important;/);\n});''')
    text = replace_test(text, "running applications panel is located in the left side panel", '''test("running applications panel is native to the Apps drawer", () => {\n  const appsSlot = html.indexOf('data-slot="apps"');\n  const filesSlot = html.indexOf('data-slot="files"');\n  const panel = html.indexOf('id="running-app-select"');\n  assert.ok(appsSlot >= 0 && panel > appsSlot && panel < filesSlot);\n  assert.match(html, /id="running-app-move"/);\n});''')
    text = replace_test(text, "Phase 9 controls use compact labels and old gate checkboxes are removed", '''test("file controls use the accepted production labels", () => {\n  for (const label of [">Load<", ">Browse<", ">Download<", ">Reset<"]) assert.match(html, new RegExp(label));\n  for (const required of ["Destination folder", "File sync", "Transfer queue"]) assert.match(html, new RegExp(required));\n  for (const old of ["Upload selected file(s)", "Automatic two-way folder sync", "PC destination", "data-gate4-check", "data-gate5-check", "data-gate6-check", "data-gate7-check"]) assert.equal(html.includes(old), false);\n  assert.match(css, /\\.uniform-buttons > button \\{ min-height: 2\\.55rem; height: 2\\.55rem;/);\n  assert.match(css, /#screen \\{ cursor: default; \\}/);\n});''')
    text = replace_test(text, "Phase 9 audio reconnect clipboard layout and settings controls are present", '''test("audio reconnect clipboard and settings controls are present without layout modes", () => {\n  for (const id of ["audio-enabled", "audio-mute", "audio-volume", "auto-reconnect", "reconnect", "clipboard-auto-sync", "clipboard-max-kib", "clipboard-copy-android", "settings-export", "settings-import"]) assert.match(html, new RegExp(`id=\\"${id}\\"`));\n  assert.equal(html.includes('id="workspace-layout"'), false);\n  assert.equal(controllerSource.includes("workspaceLayout"), false);\n  assert.match(css, /:focus-visible/);\n});''')
    text = replace_test(text, "side cards are collapsible and expanded by default", '''test("native drawer uses persisted accordions only for multi-section groups", () => {\n  assert.match(html, /id="gb-single-drawer-root"/);\n  assert.match(html, /data-section-key="files-load"/);\n  assert.match(html, /data-section-key="access-web-browser"/);\n  assert.equal(mainSource.includes("initializeCollapsibleCards"), false);\n  assert.equal(html.includes("card-collapse-button"), false);\n});''')
    text = replace_test(text, "focus layout is reversible from the always-visible header selector", '''test("Focus-style workspace is permanent and has no layout selector", () => {\n  const headerStart = html.indexOf('<header class="topbar">');\n  const headerEnd = html.indexOf('</header>', headerStart);\n  const header = html.slice(headerStart, headerEnd);\n  assert.match(header, /id="fullscreen"/);\n  assert.equal(header.includes('id="workspace-layout"'), false);\n  assert.equal(controllerSource.includes("applyWorkspaceLayout"), false);\n  assert.equal(controllerSource.includes("workspaceLayout"), false);\n});''')
    text = replace_test(text, "two-way watched-folder controls are present", '''test("File sync controls are present", () => {\n  for (const id of ["auto-download-enabled", "auto-upload-enabled", "auto-upload-duplicate", "auto-upload-existing"]) assert.match(html, new RegExp(`id="${id}"`));\n  assert.match(html, /File sync/);\n  assert.equal(html.includes("Automatic two-way folder sync"), false);\n  assert.match(html, /Files created by one sync direction are fingerprinted/);\n});''')
    write(path, text)


def add_brand_regression() -> None:
    write(ROOT / "tests" / "ux" / "test_droidwebdisplay_branding.py", '''from pathlib import Path\n\n\ndef test_web_client_has_no_legacy_gpt_bridge_branding() -> None:\n    root = Path(__file__).resolve().parents[2]\n    web = root / "apps" / "web-client"\n    legacy = ("GptBridge", "GPT Bridge", "Gpt-Bridge", "gpt_bridge", "gpt-bridge", "gptBridge")\n    offenders = []\n    for path in [web / "static" / "index.html", web / "static" / "droidwebdisplay-main-drawer.js", web / "src" / "main.ts", web / "src" / "controller.ts"]:\n        text = path.read_text(encoding="utf-8")\n        for token in legacy:\n            if token in text:\n                offenders.append(f"{path.relative_to(root)}: {token}")\n    assert offenders == []\n\n\ndef test_native_single_drawer_is_source_of_truth() -> None:\n    root = Path(__file__).resolve().parents[2]\n    html = (root / "apps" / "web-client" / "static" / "index.html").read_text(encoding="utf-8")\n    assert 'data-ui="droidwebdisplay-native-single-drawer-v1"' in html\n    assert 'id="gb-single-drawer-root"' in html\n    assert '<aside class="sidepanel">' not in html\n    assert '<aside class="transfer-panel"' not in html\n    assert 'id="workspace-layout"' not in html\n    for label in ("Apps", "Files", "Clipboard", "Display", "Audio", "Access", "Network", "Diagnostics", "Settings"):\n        assert f'>{label}<' in html\n''')


def scan_web_branding() -> None:
    legacy = ("GptBridge", "GPT Bridge", "Gpt-Bridge", "gpt_bridge", "gpt-bridge", "gptBridge")
    offenders = []
    for path in [STATIC / "index.html", STATIC / "droidwebdisplay-main-drawer.js", WEB / "src" / "main.ts", WEB / "src" / "controller.ts"]:
        text = read(path)
        for token in legacy:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {token}")
    if offenders:
        raise RuntimeError("Legacy branding remains:\n" + "\n".join(offenders))


def main() -> int:
    migrate_html(); migrate_drawer_js(); migrate_controller(); migrate_main(); migrate_css(); migrate_layout_tests(); add_brand_regression(); scan_web_branding()
    print("Native DroidWebDisplay UI migration complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
