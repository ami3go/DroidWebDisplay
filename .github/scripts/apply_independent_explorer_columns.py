from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing expected text in {path}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


js = "apps/web-client/static/droidwebdisplay-main-drawer.js"
css = "apps/web-client/static/droidwebdisplay-main-drawer.css"
html = "apps/web-client/static/index.html"
test = "apps/web-client/tests/connect-drawer.test.mjs"

replace_once(js, "/* DroidWebDisplay native single-drawer controller v1.6.0 */", "/* DroidWebDisplay native single-drawer controller v1.7.0 */")
replace_once(js, "  const EXPLORER_COLUMNS_KEY = 'droidwebdisplay.ui.explorer.columns.v1';", "  const EXPLORER_COLUMNS_KEY = 'droidwebdisplay.ui.explorer.columns.v2';")

start = "  function loadExplorerColumnState() {\n"
end = "  function boot() {\n"
text = Path(js).read_text(encoding="utf-8")
si = text.index(start)
ei = text.index(end, si)
new_block = r'''  function loadExplorerColumnState() {
    try {
      const state = JSON.parse(get(EXPLORER_COLUMNS_KEY, '{}')) || {};
      return {
        name: Number.isFinite(Number(state.name)) ? Number(state.name) : null,
        size: Number.isFinite(Number(state.size)) ? Number(state.size) : null,
        modified: Number.isFinite(Number(state.modified)) ? Number(state.modified) : null,
      };
    } catch (_) {
      return { name: null, size: null, modified: null };
    }
  }
  function bindExplorerColumnResize() {
    const ui = root();
    const frame = ui?.querySelector('.gb-drawer-slot[data-slot="files"] .explorer-frame');
    const nameHeader = frame?.querySelector('.explorer-header-button.name-cell');
    const sizeHeader = frame?.querySelector('.explorer-header-button.size-cell');
    const modifiedHeader = frame?.querySelector('.explorer-header-button.modified-cell');
    if (!frame || !nameHeader || !sizeHeader || !modifiedHeader) return;

    const columns = {
      name: { header: nameHeader, property: '--dwd-explorer-name-w', min: 80, max: 720 },
      size: { header: sizeHeader, property: '--dwd-explorer-size-w', min: 54, max: 280 },
      modified: { header: modifiedHeader, property: '--dwd-explorer-modified-w', min: 78, max: 420 },
    };
    const state = loadExplorerColumnState();
    const save = () => set(EXPLORER_COLUMNS_KEY, JSON.stringify(state));
    const applyColumn = (key, width, persist = false) => {
      const column = columns[key];
      if (!column || !Number.isFinite(width)) return;
      const next = Math.round(Math.min(column.max, Math.max(column.min, width)));
      state[key] = next;
      frame.style.setProperty(column.property, `${next}px`);
      if (persist) save();
    };
    const resetColumn = key => {
      const column = columns[key];
      if (!column) return;
      state[key] = null;
      frame.style.removeProperty(column.property);
      save();
    };
    for (const key of Object.keys(columns)) {
      if (state[key] !== null) applyColumn(key, state[key]);
    }

    const addHandle = key => {
      const column = columns[key];
      const header = column.header;
      if (header.querySelector('.explorer-column-resizer')) return;
      const handle = document.createElement('span');
      handle.className = 'explorer-column-resizer';
      handle.dataset.column = key;
      handle.setAttribute('role', 'separator');
      handle.setAttribute('aria-orientation', 'vertical');
      handle.setAttribute('aria-label', `Resize ${key[0].toUpperCase()}${key.slice(1)} column`);
      handle.tabIndex = 0;
      handle.title = `Drag to resize ${key} · Double-click to reset`;
      header.append(handle);

      let pointer = null;
      let startX = 0;
      let startWidth = 0;
      const finish = event => {
        if (pointer === null || (event?.pointerId !== undefined && event.pointerId !== pointer)) return;
        pointer = null;
        frame.classList.remove('column-resizing');
        applyColumn(key, header.getBoundingClientRect().width, true);
      };
      handle.addEventListener('click', event => event.stopPropagation());
      handle.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.stopPropagation();
        pointer = event.pointerId;
        startX = event.clientX;
        startWidth = header.getBoundingClientRect().width;
        handle.setPointerCapture?.(event.pointerId);
        frame.classList.add('column-resizing');
      });
      handle.addEventListener('pointermove', event => {
        if (pointer !== event.pointerId) return;
        applyColumn(key, startWidth + event.clientX - startX);
      });
      handle.addEventListener('pointerup', finish);
      handle.addEventListener('pointercancel', finish);
      handle.addEventListener('dblclick', event => {
        event.preventDefault();
        event.stopPropagation();
        resetColumn(key);
      });
      handle.addEventListener('keydown', event => {
        if (event.key === 'Home') {
          event.preventDefault();
          resetColumn(key);
          return;
        }
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        const delta = event.key === 'ArrowRight' ? 8 : -8;
        applyColumn(key, header.getBoundingClientRect().width + delta, true);
      });
    };
    addHandle('name');
    addHandle('size');
    addHandle('modified');
  }
'''
Path(js).write_text(text[:si] + new_block + text[ei:], encoding="utf-8")

replace_once(
    css,
    "  grid-template-columns: 26px minmax(80px, 1fr) var(--dwd-explorer-size-w, 54px) var(--dwd-explorer-modified-w, 78px) 26px;",
    "  grid-template-columns: 26px var(--dwd-explorer-name-w, minmax(80px, 1fr)) var(--dwd-explorer-size-w, 54px) var(--dwd-explorer-modified-w, 78px) 26px;",
)
replace_once(
    css,
    "#gb-single-drawer-root .gb-drawer-slot[data-slot=\"files\"] .explorer-frame {\n  width: 100%;\n  min-width: 0;\n}",
    "#gb-single-drawer-root .gb-drawer-slot[data-slot=\"files\"] .explorer-frame {\n  width: 100%;\n  min-width: 0;\n  overflow-x: auto;\n}",
)

# Replace tests for previous pairwise behavior with explicit independent-column expectations.
t = Path(test).read_text(encoding="utf-8")
marker = 'test("File Explorer columns are user resizable and persisted"'
if marker in t:
    si = t.index(marker)
    # Tests are appended at the end; remove from this test onward and reappend corrected assertions.
    t = t[:si].rstrip() + "\n\n"
new_test = r'''test("File Explorer Name, Size and Modified columns resize independently", () => {
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
'''
Path(test).write_text(t + new_test, encoding="utf-8")

replace_once(html, "droidwebdisplay-main-drawer.css?v=0.11.2-native3", "droidwebdisplay-main-drawer.css?v=0.11.2-native4") if "native3" in Path(html).read_text(encoding="utf-8") else replace_once(html, "droidwebdisplay-main-drawer.css?v=0.11.2-native2", "droidwebdisplay-main-drawer.css?v=0.11.2-native4")
replace_once(html, "droidwebdisplay-main-drawer.js?v=0.11.2-native3", "droidwebdisplay-main-drawer.js?v=0.11.2-native4") if "droidwebdisplay-main-drawer.js?v=0.11.2-native3" in Path(html).read_text(encoding="utf-8") else replace_once(html, "droidwebdisplay-main-drawer.js?v=0.11.2-native2", "droidwebdisplay-main-drawer.js?v=0.11.2-native4")
