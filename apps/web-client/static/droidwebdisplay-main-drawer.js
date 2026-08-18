/* DroidWebDisplay native single-drawer controller v1.8.0 */
(() => {
  'use strict';
  const PIN_KEY = 'droidwebdisplay.ui.drawer.pinned.v1';
  const LAST_GROUP_KEY = 'droidwebdisplay.ui.drawer.lastGroup.v1';
  const ACCORDION_KEY = 'droidwebdisplay.ui.drawer.accordions.v1';
  const DRAWER_WIDTH_KEY = 'droidwebdisplay.ui.drawer.width.v1';
  const EXPLORER_COLUMNS_KEY = 'droidwebdisplay.ui.explorer.columns.v2';
  const DRAWER_MIN_WIDTH = 280;
  const DRAWER_MAX_WIDTH = 720;
  const ROOT_ID = 'gb-single-drawer-root';
  const GROUPS = ['display','clipboard','files','audio','access','diagnostics','settings'];
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
  function installBrandHeaderRedesign() {
    const brand = document.querySelector('.topbar-brand');
    const title = brand?.querySelector('h1');
    if (!brand || !title) return;

    if (!document.getElementById('brand-header-redesign-style')) {
      const style = document.createElement('style');
      style.id = 'brand-header-redesign-style';
      style.textContent = `
        .topbar {
          min-height: 2.92rem;
          padding: 0 .85rem 0 0;
        }
        .topbar-brand {
          position: relative;
          height: 2.92rem;
          min-height: 2.92rem;
          min-width: 12.5rem;
          padding-left: 3.34rem;
          gap: 0;
          justify-content: flex-start;
        }
        .brand-device-status {
          position: absolute;
          inset: 0 auto 0 0;
          width: 2.92rem;
          height: 2.92rem;
          display: grid;
          place-items: center;
          border-right: 1px solid #242a37;
          background: linear-gradient(180deg, #151c29 0%, #0d121b 100%);
          color: #758197;
          overflow: hidden;
        }
        .brand-device-status svg {
          width: 2.62rem;
          height: 2.62rem;
          overflow: visible;
        }
        .brand-phone, .brand-display, .brand-device-link {
          color: #758197;
          transition: color 180ms ease, filter 180ms ease, opacity 180ms ease;
        }
        .brand-phone-frame, .brand-display-frame, .brand-display-stand,
        .brand-device-link, .brand-phone-speaker {
          fill: none;
          stroke: currentColor;
          stroke-width: 2.15;
          stroke-linecap: round;
          stroke-linejoin: round;
          vector-effect: non-scaling-stroke;
        }
        .brand-phone-screen, .brand-display-screen {
          fill: #0a0d13;
          stroke: currentColor;
          stroke-width: 1.45;
          vector-effect: non-scaling-stroke;
        }
        .brand-phone-home { fill: currentColor; }
        .topbar-brand[data-phone-found="true"] .brand-phone {
          color: #69d9a2;
          filter: drop-shadow(0 0 5px #36c98242);
        }
        .topbar-brand[data-connection-state="connecting"] .brand-display {
          color: #82a6ff;
          animation: brand-display-pulse 1.05s ease-in-out infinite;
        }
        .topbar-brand[data-connection-state="connected"] .brand-display,
        .topbar-brand[data-connection-state="connected"] .brand-device-link {
          color: #69d9a2;
          filter: drop-shadow(0 0 5px #36c98242);
        }
        .topbar-brand > h1 {
          flex: 0 0 1.46rem;
          height: 1.46rem;
          margin: 0;
          display: flex;
          align-items: flex-end;
          padding-bottom: .08rem;
          color: #f3f6fb;
          font-size: 1.04rem;
          line-height: 1;
          letter-spacing: -.02em;
          transition: color 180ms ease, text-shadow 180ms ease;
        }
        .topbar-brand[data-connection-state="connected"] > h1 {
          color: #69d9a2;
          text-shadow: 0 0 12px #36c98222;
        }
        .topbar-brand > .connection-status {
          height: 1.46rem;
          min-height: 1.46rem;
          max-width: 15rem;
          gap: .28rem;
          padding: 0;
          border-color: transparent;
          background: transparent;
          box-shadow: none;
        }
        .topbar-brand > .connection-status strong {
          font-size: .66rem;
          font-weight: 650;
        }
        .topbar-brand > .connection-status .connection-status-icon {
          width: .84rem;
          height: .84rem;
        }
        .topbar-brand > .connection-status[data-state="connected"],
        .topbar-brand > .connection-status[data-state="disconnected"],
        .topbar-brand > .connection-status[data-state="connecting"] {
          border-color: transparent;
          background: transparent;
          box-shadow: none;
        }
        @keyframes brand-display-pulse {
          0%, 100% { opacity: .72; }
          50% { opacity: 1; filter: drop-shadow(0 0 6px #82a6ff55); }
        }
        @media (prefers-reduced-motion: reduce) {
          .topbar-brand[data-connection-state="connecting"] .brand-display { animation: none; }
        }
      `;
      document.head.append(style);
    }

    if (!brand.querySelector('.brand-device-status')) {
      const mark = document.createElement('span');
      mark.className = 'brand-device-status';
      mark.setAttribute('aria-hidden', 'true');
      mark.innerHTML = `
        <svg viewBox="0 0 64 64" focusable="false">
          <g class="brand-display">
            <rect class="brand-display-frame" x="28.5" y="11.5" width="31" height="27" rx="3.5"></rect>
            <path class="brand-display-stand" d="M44 38.5v8M35.5 49.5h17"></path>
            <path class="brand-display-screen" d="M33.5 17h21v16.5h-21z"></path>
          </g>
          <path class="brand-device-link" d="M25.5 31.5h5"></path>
          <g class="brand-phone">
            <rect class="brand-phone-frame" x="5" y="8.5" width="22" height="47" rx="5"></rect>
            <rect class="brand-phone-screen" x="8.5" y="15" width="15" height="31" rx="1.8"></rect>
            <path class="brand-phone-speaker" d="M11.5 12h9"></path>
            <circle class="brand-phone-home" cx="16" cy="51" r="1.4"></circle>
          </g>
        </svg>`;
      brand.insertBefore(mark, title);
    }
  }

  function bindBrandHeaderStatus() {
    const brand = document.querySelector('.topbar-brand');
    const device = document.getElementById('device');
    const status = document.getElementById('connection-status');
    if (!brand || !(device instanceof HTMLSelectElement) || !status || brand.dataset.statusBound === '1') return;
    brand.dataset.statusBound = '1';

    const sync = () => {
      const phoneFound = [...device.options].some(option => Boolean(option.value) && !option.disabled);
      brand.dataset.phoneFound = phoneFound ? 'true' : 'false';
      brand.dataset.connectionState = status.dataset.state || 'disconnected';
    };
    const deviceObserver = new MutationObserver(sync);
    deviceObserver.observe(device, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'value'] });
    device.addEventListener('change', sync);
    const statusObserver = new MutationObserver(sync);
    statusObserver.observe(status, { attributes: true, attributeFilter: ['data-state'] });
    sync();
  }
  function bindStatusActivityIndicator() {
    const statusContainer = document.getElementById('connection-status');
    const statusIcon = document.getElementById('status-icon');
    const statusLabel = document.getElementById('status');
    const svg = statusIcon?.querySelector('svg');
    if (!statusContainer || !statusIcon || !statusLabel || !svg || statusIcon.dataset.activityBound === '1') return;
    statusIcon.dataset.activityBound = '1';

    const svgNamespace = 'http://www.w3.org/2000/svg';
    const actionDuration = 1100;
    const actionPaths = {
      navigation: 'M15.5 7.5 11 12l4.5 4.5M11 12h6',
      clipboard: 'M9.25 8.5h5.5v7h-5.5zM10.5 8.5V7h3v1.5',
      rotate: 'M16.25 9.1A5 5 0 1 0 17 14M16.25 6.75V9.1h-2.35',
      resize: 'M9.5 8H8v1.5M14.5 8H16v1.5M16 14.5V16h-1.5M9.5 16H8v-1.5M10 14l-2 2M14 10l2-2',
      power: 'M12 7v5M8.6 9.4a5 5 0 1 0 6.8 0',
      fullscreen: 'M10 8H8v2M14 8h2v2M16 14v2h-2M10 16H8v-2',
      apps: 'M8 8h3v3H8zM13 8h3v3h-3zM8 13h3v3H8zM13 13h3v3h-3z',
      warning: 'M12 8.2v4.5M12 15.6v.2',
    };
    const check = svg.querySelector('.status-check');
    const offline = svg.querySelector('.status-offline');
    const actionGlyph = document.createElementNS(svgNamespace, 'path');
    actionGlyph.classList.add('status-action-glyph');
    actionGlyph.setAttribute('fill', 'none');
    actionGlyph.setAttribute('stroke', 'currentColor');
    actionGlyph.setAttribute('stroke-width', '1.9');
    actionGlyph.setAttribute('stroke-linecap', 'round');
    actionGlyph.setAttribute('stroke-linejoin', 'round');
    actionGlyph.setAttribute('vector-effect', 'non-scaling-stroke');
    actionGlyph.style.opacity = '0';
    actionGlyph.style.transformOrigin = '12px 12px';
    svg.append(actionGlyph);

    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    let resetTimer = null;
    let glyphAnimation = null;
    let iconAnimation = null;
    let lastStatus = statusLabel.textContent?.trim() || '';
    let lastState = statusContainer.dataset.state || 'disconnected';

    const actionForStatus = title => {
      const text = String(title || '').toLowerCase();
      if (/error|failed|stopped|skipped|limited|not confirmed/.test(text)) return 'warning';
      if (text.includes('clipboard') || text.includes('pasting') || text.includes('text fallback')) return 'clipboard';
      if (text.includes('rotat')) return 'rotate';
      if (text.includes('resiz')) return 'resize';
      return null;
    };

    const restoreSteadyGlyph = () => {
      if (resetTimer !== null) window.clearTimeout(resetTimer);
      resetTimer = null;
      glyphAnimation?.cancel();
      iconAnimation?.cancel();
      glyphAnimation = null;
      iconAnimation = null;
      actionGlyph.style.opacity = '0';
      actionGlyph.removeAttribute('d');
      delete statusIcon.dataset.action;
      check?.style.removeProperty('opacity');
      offline?.style.removeProperty('opacity');
    };

    const showAction = action => {
      const path = actionPaths[action];
      if (!path) return;
      restoreSteadyGlyph();
      actionGlyph.setAttribute('d', path);
      statusIcon.dataset.action = action;
      if (check) check.style.opacity = '0';
      if (offline) offline.style.opacity = '0';
      actionGlyph.style.opacity = '1';

      if (!reducedMotion?.matches && typeof actionGlyph.animate === 'function') {
        glyphAnimation = actionGlyph.animate([
          { opacity: 0, transform: 'scale(.72)' },
          { opacity: 1, transform: 'scale(1.08)', offset: 0.22 },
          { opacity: 1, transform: 'scale(1)', offset: 0.72 },
          { opacity: 0, transform: 'scale(.9)' },
        ], { duration: actionDuration, easing: 'cubic-bezier(.2,.8,.2,1)', fill: 'forwards' });
        iconAnimation = statusIcon.animate([
          { transform: 'scale(1)' },
          { transform: 'scale(1.22)', offset: 0.28 },
          { transform: 'scale(1)' },
        ], { duration: 460, easing: 'cubic-bezier(.2,.8,.2,1)' });
      }
      resetTimer = window.setTimeout(restoreSteadyGlyph, reducedMotion?.matches ? 760 : actionDuration);
    };

    const animateConnectionState = nextState => {
      if (!nextState || nextState === lastState) return;
      restoreSteadyGlyph();
      if (!reducedMotion?.matches && typeof statusIcon.animate === 'function') {
        if (nextState === 'connected') {
          iconAnimation = statusIcon.animate([
            { transform: 'scale(.76)', opacity: .6 },
            { transform: 'scale(1.18)', opacity: 1, offset: .58 },
            { transform: 'scale(1)', opacity: 1 },
          ], { duration: 420, easing: 'cubic-bezier(.2,.8,.2,1)' });
        } else if (nextState === 'disconnected') {
          iconAnimation = statusIcon.animate([
            { transform: 'scale(1)', opacity: 1 },
            { transform: 'scale(.82)', opacity: .58, offset: .5 },
            { transform: 'scale(1)', opacity: 1 },
          ], { duration: 320, easing: 'ease-out' });
        }
      }
      lastState = nextState;
    };

    const statusObserver = new MutationObserver(() => {
      const title = statusLabel.textContent?.trim() || '';
      if (!title || title === lastStatus) return;
      lastStatus = title;
      const action = actionForStatus(title);
      if (action) showAction(action);
    });
    statusObserver.observe(statusLabel, { childList: true, characterData: true, subtree: true });

    const stateObserver = new MutationObserver(() => animateConnectionState(statusContainer.dataset.state || 'disconnected'));
    stateObserver.observe(statusContainer, { attributes: true, attributeFilter: ['data-state'] });

    const controlActions = {
      back: 'navigation',
      home: 'navigation',
      recent: 'navigation',
      power: 'power',
      fullscreen: 'fullscreen',
      'running-app-icon': 'apps',
    };
    for (const [id, action] of Object.entries(controlActions)) {
      document.getElementById(id)?.addEventListener('click', () => showAction(action));
    }
    document.getElementById('running-app-select')?.addEventListener('change', () => showAction('apps'));
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
      // Re-clamp to the new viewport for display only. Persisting here would
      // overwrite a wider saved preference the moment the window is narrowed,
      // and it could never be recovered by widening the window again.
      if (Number.isFinite(current)) applyDrawerWidth(current, false);
    });
  }
  function loadExplorerColumnState() {
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
  function boot() {
    const ui = root(); if (!ui) return;
    document.documentElement.classList.add('gb-single-drawer-enabled');
    installBrandHeaderRedesign();
    bindStatusShortcut();
    bindBrandHeaderStatus();
    bindStatusActivityIndicator();
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