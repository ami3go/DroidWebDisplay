from __future__ import annotations

import argparse
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing expected text in {path}: {old[:120]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def append_once(path: str, marker: str, content: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if marker in text:
        return
    file.write_text(text.rstrip() + "\n\n" + content.strip() + "\n", encoding="utf-8")


def drawer_phase() -> None:
    js = "apps/web-client/static/droidwebdisplay-main-drawer.js"
    css = "apps/web-client/static/droidwebdisplay-main-drawer.css"
    html = "apps/web-client/static/index.html"
    test = "apps/web-client/tests/connect-drawer.test.mjs"

    replace_once(js, "/* DroidWebDisplay native single-drawer controller v1.4.0 */", "/* DroidWebDisplay native single-drawer controller v1.5.0 */")
    replace_once(
        js,
        "  const ACCORDION_KEY = 'droidwebdisplay.ui.drawer.accordions.v1';\n",
        "  const ACCORDION_KEY = 'droidwebdisplay.ui.drawer.accordions.v1';\n"
        "  const DRAWER_WIDTH_KEY = 'droidwebdisplay.ui.drawer.width.v1';\n"
        "  const DRAWER_MIN_WIDTH = 280;\n"
        "  const DRAWER_MAX_WIDTH = 720;\n",
    )
    drawer_functions = r'''  function drawerWidthBounds() {
    const rail = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--gb-rail-w')) || 58;
    return {
      min: DRAWER_MIN_WIDTH,
      max: Math.max(DRAWER_MIN_WIDTH, Math.min(DRAWER_MAX_WIDTH, window.innerWidth - rail - 120)),
    };
  }
  function applyDrawerWidth(width, persist = false) {
    const bounds = drawerWidthBounds();
    const next = Math.round(Math.min(bounds.max, Math.max(bounds.min, Number(width) || bounds.min)));
    document.documentElement.style.setProperty('--gb-drawer-w', `${next}px`);
    if (persist) set(DRAWER_WIDTH_KEY, String(next));
    return next;
  }
  function resetDrawerWidth() {
    document.documentElement.style.removeProperty('--gb-drawer-w');
    try { localStorage.removeItem(DRAWER_WIDTH_KEY); } catch (_) {}
  }
  function bindDrawerResize() {
    const panel = drawer();
    if (!panel || panel.querySelector('.gb-drawer-resize-handle')) return;
    const stored = Number.parseInt(get(DRAWER_WIDTH_KEY, ''), 10);
    if (Number.isFinite(stored)) applyDrawerWidth(stored);

    const handle = document.createElement('div');
    handle.className = 'gb-drawer-resize-handle';
    handle.setAttribute('role', 'separator');
    handle.setAttribute('aria-orientation', 'vertical');
    handle.setAttribute('aria-label', 'Resize drawer');
    handle.tabIndex = 0;
    handle.title = 'Drag to resize drawer · Double-click to reset';
    panel.append(handle);

    let startX = 0;
    let startWidth = 0;
    let activePointer = null;
    const finish = () => {
      if (activePointer === null) return;
      activePointer = null;
      document.documentElement.classList.remove('gb-drawer-resizing');
      const width = panel.getBoundingClientRect().width;
      applyDrawerWidth(width, true);
    };
    handle.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      event.preventDefault();
      startX = event.clientX;
      startWidth = panel.getBoundingClientRect().width;
      activePointer = event.pointerId;
      handle.setPointerCapture?.(event.pointerId);
      document.documentElement.classList.add('gb-drawer-resizing');
    });
    handle.addEventListener('pointermove', event => {
      if (activePointer !== event.pointerId) return;
      applyDrawerWidth(startWidth + event.clientX - startX);
    });
    handle.addEventListener('pointerup', finish);
    handle.addEventListener('pointercancel', finish);
    handle.addEventListener('dblclick', event => {
      event.preventDefault();
      resetDrawerWidth();
    });
    handle.addEventListener('keydown', event => {
      if (event.key === 'Home') {
        event.preventDefault();
        resetDrawerWidth();
        return;
      }
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      const delta = event.key === 'ArrowRight' ? 16 : -16;
      applyDrawerWidth(panel.getBoundingClientRect().width + delta, true);
    });
    window.addEventListener('resize', () => {
      const current = Number.parseInt(get(DRAWER_WIDTH_KEY, ''), 10);
      if (Number.isFinite(current)) applyDrawerWidth(current, true);
    });
  }
'''
    replace_once(js, "  function boot() {\n", drawer_functions + "  function boot() {\n")
    replace_once(js, "    bindDrawerKeyboard();\n", "    bindDrawerKeyboard();\n    bindDrawerResize();\n")

    drawer_css = r'''
.gb-drawer-resize-handle {
  position: absolute;
  z-index: 12;
  top: 0;
  right: -5px;
  bottom: 0;
  width: 10px;
  cursor: ew-resize;
  touch-action: none;
}
.gb-drawer-resize-handle::after {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 4px;
  width: 2px;
  background: transparent;
  transition: background .12s ease;
}
.gb-drawer-resize-handle:hover::after,
.gb-drawer-resize-handle:focus-visible::after,
html.gb-drawer-resizing .gb-drawer-resize-handle::after { background: var(--dwd-cyan); }
.gb-drawer-resize-handle:focus-visible { outline: none; }
html.gb-drawer-resizing, html.gb-drawer-resizing * { cursor: ew-resize !important; user-select: none !important; }
'''
    replace_once(css, ".gb-drawer.gb-open { transform: translateX(0); }\n", ".gb-drawer.gb-open { transform: translateX(0); }\n" + drawer_css)

    replace_once(test, "const connectCss = await readFile(resolve(root, \"static/droidwebdisplay-connect-drawer.css\"), \"utf8\");\n", "const connectCss = await readFile(resolve(root, \"static/droidwebdisplay-connect-drawer.css\"), \"utf8\");\nconst drawerCss = await readFile(resolve(root, \"static/droidwebdisplay-main-drawer.css\"), \"utf8\");\n")
    append_once(
        test,
        'test("drawer width is user resizable and persisted"',
        r'''test("drawer width is user resizable and persisted", () => {
  assert.match(drawerSource, /DRAWER_WIDTH_KEY = 'droidwebdisplay\.ui\.drawer\.width\.v1'/);
  assert.match(drawerSource, /function bindDrawerResize\(\)/);
  assert.match(drawerSource, /gb-drawer-resize-handle/);
  assert.match(drawerSource, /addEventListener\('pointerdown'/);
  assert.match(drawerSource, /addEventListener\('pointermove'/);
  assert.match(drawerSource, /addEventListener\('dblclick'/);
  assert.match(drawerSource, /style\.setProperty\('--gb-drawer-w'/);
  assert.match(drawerCss, /\.gb-drawer-resize-handle \{/);
  assert.match(drawerCss, /cursor: ew-resize/);
});''',
    )

    replace_once(html, "droidwebdisplay-main-drawer.css?v=0.11.2-native1", "droidwebdisplay-main-drawer.css?v=0.11.2-native2")
    replace_once(html, "droidwebdisplay-main-drawer.js?v=0.11.2-native1", "droidwebdisplay-main-drawer.js?v=0.11.2-native2")


def columns_phase() -> None:
    js = "apps/web-client/static/droidwebdisplay-main-drawer.js"
    css = "apps/web-client/static/droidwebdisplay-main-drawer.css"
    html = "apps/web-client/static/index.html"
    test = "apps/web-client/tests/connect-drawer.test.mjs"

    replace_once(js, "/* DroidWebDisplay native single-drawer controller v1.5.0 */", "/* DroidWebDisplay native single-drawer controller v1.6.0 */")
    replace_once(
        js,
        "  const DRAWER_WIDTH_KEY = 'droidwebdisplay.ui.drawer.width.v1';\n",
        "  const DRAWER_WIDTH_KEY = 'droidwebdisplay.ui.drawer.width.v1';\n"
        "  const EXPLORER_COLUMNS_KEY = 'droidwebdisplay.ui.explorer.columns.v1';\n",
    )
    functions = r'''  function loadExplorerColumnState() {
    try {
      const state = JSON.parse(get(EXPLORER_COLUMNS_KEY, '{}')) || {};
      return {
        size: Number.isFinite(Number(state.size)) ? Number(state.size) : null,
        modified: Number.isFinite(Number(state.modified)) ? Number(state.modified) : null,
      };
    } catch (_) {
      return { size: null, modified: null };
    }
  }
  function bindExplorerColumnResize() {
    const ui = root();
    const frame = ui?.querySelector('.gb-drawer-slot[data-slot="files"] .explorer-frame');
    const nameHeader = frame?.querySelector('.explorer-header-button.name-cell');
    const sizeHeader = frame?.querySelector('.explorer-header-button.size-cell');
    const modifiedHeader = frame?.querySelector('.explorer-header-button.modified-cell');
    if (!frame || !nameHeader || !sizeHeader || !modifiedHeader) return;

    const apply = (size, modified, persist = false) => {
      if (Number.isFinite(size)) frame.style.setProperty('--dwd-explorer-size-w', `${Math.round(size)}px`);
      if (Number.isFinite(modified)) frame.style.setProperty('--dwd-explorer-modified-w', `${Math.round(modified)}px`);
      if (persist) set(EXPLORER_COLUMNS_KEY, JSON.stringify({ size: Math.round(size), modified: Math.round(modified) }));
    };
    const reset = () => {
      frame.style.removeProperty('--dwd-explorer-size-w');
      frame.style.removeProperty('--dwd-explorer-modified-w');
      try { localStorage.removeItem(EXPLORER_COLUMNS_KEY); } catch (_) {}
    };
    const stored = loadExplorerColumnState();
    if (stored.size !== null && stored.modified !== null) apply(stored.size, stored.modified);

    const addHandle = (header, boundary) => {
      if (header.querySelector('.explorer-column-resizer')) return;
      const handle = document.createElement('span');
      handle.className = 'explorer-column-resizer';
      handle.dataset.boundary = boundary;
      handle.setAttribute('role', 'separator');
      handle.setAttribute('aria-orientation', 'vertical');
      handle.setAttribute('aria-label', `Resize ${boundary === 'name-size' ? 'Name and Size' : 'Size and Modified'} columns`);
      handle.tabIndex = 0;
      handle.title = 'Drag to resize columns · Double-click to reset';
      header.append(handle);

      let pointer = null;
      let startX = 0;
      let startName = 0;
      let startSize = 0;
      let startModified = 0;
      const finish = event => {
        if (pointer === null || (event?.pointerId !== undefined && event.pointerId !== pointer)) return;
        pointer = null;
        frame.classList.remove('column-resizing');
        apply(sizeHeader.getBoundingClientRect().width, modifiedHeader.getBoundingClientRect().width, true);
      };
      handle.addEventListener('click', event => event.stopPropagation());
      handle.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.stopPropagation();
        pointer = event.pointerId;
        startX = event.clientX;
        startName = nameHeader.getBoundingClientRect().width;
        startSize = sizeHeader.getBoundingClientRect().width;
        startModified = modifiedHeader.getBoundingClientRect().width;
        handle.setPointerCapture?.(event.pointerId);
        frame.classList.add('column-resizing');
      });
      handle.addEventListener('pointermove', event => {
        if (pointer !== event.pointerId) return;
        const raw = event.clientX - startX;
        if (boundary === 'name-size') {
          const delta = Math.max(80 - startName, Math.min(startSize - 54, raw));
          apply(startSize - delta, startModified);
        } else {
          const delta = Math.max(54 - startSize, Math.min(startModified - 78, raw));
          apply(startSize + delta, startModified - delta);
        }
      });
      handle.addEventListener('pointerup', finish);
      handle.addEventListener('pointercancel', finish);
      handle.addEventListener('dblclick', event => {
        event.preventDefault();
        event.stopPropagation();
        reset();
      });
      handle.addEventListener('keydown', event => {
        if (event.key === 'Home') {
          event.preventDefault();
          reset();
          return;
        }
        if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
        event.preventDefault();
        const direction = event.key === 'ArrowRight' ? 8 : -8;
        const nameWidth = nameHeader.getBoundingClientRect().width;
        const sizeWidth = sizeHeader.getBoundingClientRect().width;
        const modifiedWidth = modifiedHeader.getBoundingClientRect().width;
        if (boundary === 'name-size') {
          const delta = Math.max(80 - nameWidth, Math.min(sizeWidth - 54, direction));
          apply(sizeWidth - delta, modifiedWidth, true);
        } else {
          const delta = Math.max(54 - sizeWidth, Math.min(modifiedWidth - 78, direction));
          apply(sizeWidth + delta, modifiedWidth - delta, true);
        }
      });
    };
    addHandle(nameHeader, 'name-size');
    addHandle(sizeHeader, 'size-modified');
  }
'''
    replace_once(js, "  function boot() {\n", functions + "  function boot() {\n")
    replace_once(js, "    bindDrawerResize();\n", "    bindDrawerResize();\n    bindExplorerColumnResize();\n")

    replace_once(
        css,
        "  grid-template-columns: 26px minmax(80px, 1fr) 54px 78px 26px;\n",
        "  grid-template-columns: 26px minmax(80px, 1fr) var(--dwd-explorer-size-w, 54px) var(--dwd-explorer-modified-w, 78px) 26px;\n",
    )
    column_css = r'''
#gb-single-drawer-root .gb-drawer-slot[data-slot="files"] .explorer-header-button { position: relative; overflow: visible; }
#gb-single-drawer-root .gb-drawer-slot[data-slot="files"] .explorer-column-resizer {
  position: absolute;
  z-index: 5;
  top: 0;
  right: -5px;
  bottom: 0;
  width: 10px;
  cursor: col-resize;
  touch-action: none;
}
#gb-single-drawer-root .gb-drawer-slot[data-slot="files"] .explorer-column-resizer::after {
  content: "";
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 4px;
  width: 2px;
  background: transparent;
  transition: background .12s ease;
}
#gb-single-drawer-root .gb-drawer-slot[data-slot="files"] .explorer-column-resizer:hover::after,
#gb-single-drawer-root .gb-drawer-slot[data-slot="files"] .explorer-column-resizer:focus-visible::after,
#gb-single-drawer-root .gb-drawer-slot[data-slot="files"] .explorer-frame.column-resizing .explorer-column-resizer::after { background: var(--dwd-cyan); }
#gb-single-drawer-root .gb-drawer-slot[data-slot="files"] .explorer-column-resizer:focus-visible { outline: none; }
#gb-single-drawer-root .gb-drawer-slot[data-slot="files"] .explorer-frame.column-resizing,
#gb-single-drawer-root .gb-drawer-slot[data-slot="files"] .explorer-frame.column-resizing * { cursor: col-resize !important; user-select: none !important; }
@media (max-width: 560px) {
  #gb-single-drawer-root .gb-drawer-slot[data-slot="files"] .explorer-column-resizer { display: none; }
}
'''
    append_once(css, ".explorer-column-resizer {", column_css)

    append_once(
        test,
        'test("Android File Explorer columns are user resizable"',
        r'''test("Android File Explorer columns are user resizable", () => {
  assert.match(drawerSource, /EXPLORER_COLUMNS_KEY = 'droidwebdisplay\.ui\.explorer\.columns\.v1'/);
  assert.match(drawerSource, /function bindExplorerColumnResize\(\)/);
  assert.match(drawerSource, /explorer-column-resizer/);
  assert.match(drawerSource, /name-size/);
  assert.match(drawerSource, /size-modified/);
  assert.match(drawerSource, /addEventListener\('pointermove'/);
  assert.match(drawerSource, /localStorage\.removeItem\(EXPLORER_COLUMNS_KEY\)/);
  assert.match(drawerCss, /--dwd-explorer-size-w/);
  assert.match(drawerCss, /--dwd-explorer-modified-w/);
  assert.match(drawerCss, /cursor: col-resize/);
});''',
    )

    replace_once(html, "droidwebdisplay-main-drawer.css?v=0.11.2-native2", "droidwebdisplay-main-drawer.css?v=0.11.2-native3")
    replace_once(html, "droidwebdisplay-main-drawer.js?v=0.11.2-native2", "droidwebdisplay-main-drawer.js?v=0.11.2-native3")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["drawer", "columns"])
    args = parser.parse_args()
    if args.phase == "drawer":
        drawer_phase()
    else:
        columns_phase()


if __name__ == "__main__":
    main()
