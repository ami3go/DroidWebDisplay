/* DroidWebDisplay native single-drawer controller v1.6.0 */
(() => {
  'use strict';
  const PIN_KEY = 'droidwebdisplay.ui.drawer.pinned.v1';
  const LAST_GROUP_KEY = 'droidwebdisplay.ui.drawer.lastGroup.v1';
  const ACCORDION_KEY = 'droidwebdisplay.ui.drawer.accordions.v1';
  const DRAWER_WIDTH_KEY = 'droidwebdisplay.ui.drawer.width.v1';
  const EXPLORER_COLUMNS_KEY = 'droidwebdisplay.ui.explorer.columns.v1';
  const DRAWER_MIN_WIDTH = 280;
  const DRAWER_MAX_WIDTH = 720;
  const ROOT_ID = 'gb-single-drawer-root';
  const CONNECTION_STYLE_ID = 'droidwebdisplay-connect-drawer-css';
  const GROUPS = ['display','clipboard','files','audio','access','diagnostics','settings'];
  let activeGroup = null;
  let pinned = false;
  const root = () => document.getElementById(ROOT_ID);
  const drawer = () => root()?.querySelector('.gb-drawer');
  function get(key, fallback = null) { try { return localStorage.getItem(key) ?? fallback; } catch (_) { return fallback; } }
  function set(key, value) { try { localStorage.setItem(key, value); } catch (_) {} }
  function storedPinned() { return get(PIN_KEY, '0') === '1'; }
  function storedGroup() { const value = get(LAST_GROUP_KEY, 'display'); return GROUPS.includes(value) ? value : 'display'; }
  function ensureConnectionStyles() {
    if (document.getElementById(CONNECTION_STYLE_ID)) return;
    const link = document.createElement('link');
    link.id = CONNECTION_STYLE_ID;
    link.rel = 'stylesheet';
    link.href = './droidwebdisplay-connect-drawer.css?v=0.11.2-connect2';
    document.head.append(link);
  }
  function removeLegacyHeaderText() {
    const eyebrow = document.querySelector('.topbar-brand .eyebrow');
    if (eyebrow?.textContent?.trim().toUpperCase() === 'LOCAL USB BRIDGE') eyebrow.remove();
  }
  function ensureDisplayConnectionUi() {
    const ui = root();
    if (!ui) return;
    const displaySlot = ui.querySelector('.gb-drawer-slot[data-slot="display"]');
    if (!displaySlot) return;

    const device = document.getElementById('device');
    const connect = document.getElementById('connect');
    if (!device || !connect) return;

    if (displaySlot.querySelector('.connect-card')) return;

    const card = document.createElement('section');
    card.className = 'help-card connect-card';
    card.setAttribute('aria-label', 'Android device connection');

    const deviceLabel = document.createElement('label');
    deviceLabel.append(document.createTextNode('Android device'), device);

    const actions = document.createElement('div');
    actions.className = 'button-grid connect-actions';
    actions.append(connect);

    card.append(deviceLabel, actions);
    displaySlot.insertBefore(card, displaySlot.firstElementChild);
  }
  function mergeNetworkIntoAccess() {
    const ui = root();
    const accessSlot = ui?.querySelector('.gb-drawer-slot[data-slot="access"]');
    const networkSlot = ui?.querySelector('.gb-drawer-slot[data-slot="network"]');
    if (!ui || !accessSlot || !networkSlot || accessSlot.querySelector('[data-section-key="access-network"]')) return;
    const details = document.createElement('details');
    details.className = 'gb-accordion';
    details.dataset.sectionKey = 'access-network';
    const summary = document.createElement('summary');
    summary.className = 'gb-accordion-summary';
    const triangle = document.createElement('span');
    triangle.className = 'gb-accordion-triangle';
    triangle.setAttribute('aria-hidden', 'true');
    triangle.textContent = '▸';
    const label = document.createElement('span');
    label.className = 'gb-accordion-label';
    label.textContent = 'Network access';
    summary.append(triangle, label);
    const content = document.createElement('div');
    content.className = 'gb-accordion-content';
    while (networkSlot.firstChild) content.append(networkSlot.firstChild);
    details.append(summary, content);
    accessSlot.append(details);
    networkSlot.remove();
    ui.querySelector('.gb-rail-button[data-group="network"]')?.remove();
  }
  function applyRailOrder() {
    const rail = root()?.querySelector('.gb-rail');
    if (!rail) return;
    const spacer = rail.querySelector('.gb-rail-spacer');
    GROUPS.forEach(group => {
      const button = rail.querySelector(`.gb-rail-button[data-group="${group}"]`);
      if (button) rail.insertBefore(button, spacer);
    });
  }
  function applyPinned(value, persist = true) {
    pinned = Boolean(value);
    document.documentElement.classList.toggle('gb-single-drawer-pinned', pinned);
    root()?.classList.toggle('gb-pinned', pinned);
    const button = root()?.querySelector('.gb-drawer-pin');
    if (button) {
      const label = pinned ? 'Unpin drawer' : 'Pin drawer';
      button.setAttribute('aria-pressed', pinned ? 'true' : 'false');
      button.setAttribute('aria-label', label);
      button.title = label;
    }
    const closeButton = root()?.querySelector('.gb-drawer-close');
    if (closeButton) {
      const closeLabel = pinned ? 'Unpin and close drawer' : 'Close drawer';
      closeButton.setAttribute('aria-label', closeLabel);
      closeButton.title = closeLabel;
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
  function closeOrUnpinDrawer() {
    if (!root()) return;
    if (pinned) applyPinned(false);
    closeDrawer();
  }
  function bindDrawerKeyboard() {
    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape' || pinned || !drawer()?.classList.contains('gb-open')) return;
      closeDrawer();
    });
  }
  function bindStatusShortcut() {
    const status = document.getElementById('connection-status');
    if (!status) return;
    const openDisplay = () => openGroup('display');
    status.addEventListener('click', openDisplay);
    status.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      openDisplay();
    });
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
  function drawerWidthBounds() {
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
  function loadExplorerColumnState() {
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
  function boot() {
    const ui = root(); if (!ui) return;
    document.documentElement.classList.add('gb-single-drawer-enabled');
    ensureConnectionStyles();
    removeLegacyHeaderText();
    ensureDisplayConnectionUi();
    mergeNetworkIntoAccess();
    applyRailOrder();
    bindStatusShortcut();
    bindDrawerKeyboard();
    bindDrawerResize();
    bindExplorerColumnResize();
    ui.querySelectorAll('[data-group]').forEach(button => button.addEventListener('click', () => openGroup(button.dataset.group)));
    ui.querySelector('.gb-drawer-pin')?.addEventListener('click', () => applyPinned(!pinned));
    ui.querySelectorAll('[data-action="close"], .gb-drawer-close').forEach(button => button.addEventListener('click', closeOrUnpinDrawer));
    bindAccordions(); applyPinned(storedPinned(), false); if (pinned) openGroup(storedGroup());
  }
  window.DroidWebDisplayDrawer = { openGroup, closeDrawer, setPinned: value => applyPinned(Boolean(value)) };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
})();