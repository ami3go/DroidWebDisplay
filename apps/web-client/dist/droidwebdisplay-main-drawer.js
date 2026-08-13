/* DroidWebDisplay native single-drawer controller v1.2.1 */
(() => {
  'use strict';
  const PIN_KEY = 'droidwebdisplay.ui.drawer.pinned.v1';
  const LAST_GROUP_KEY = 'droidwebdisplay.ui.drawer.lastGroup.v1';
  const ACCORDION_KEY = 'droidwebdisplay.ui.drawer.accordions.v1';
  const ROOT_ID = 'gb-single-drawer-root';
  const CONNECT_STYLE_ID = 'droidwebdisplay-connect-drawer-css';
  const GROUPS = ['connect','display','clipboard','files','apps','audio','access','network','diagnostics','settings'];
  let activeGroup = null;
  let pinned = false;
  const root = () => document.getElementById(ROOT_ID);
  const drawer = () => root()?.querySelector('.gb-drawer');
  function get(key, fallback = null) { try { return localStorage.getItem(key) ?? fallback; } catch (_) { return fallback; } }
  function set(key, value) { try { localStorage.setItem(key, value); } catch (_) {} }
  function storedPinned() { return get(PIN_KEY, '0') === '1'; }
  function storedGroup() { const value = get(LAST_GROUP_KEY, 'display'); return GROUPS.includes(value) ? value : 'display'; }
  function ensureConnectStyles() {
    if (document.getElementById(CONNECT_STYLE_ID)) return;
    const link = document.createElement('link');
    link.id = CONNECT_STYLE_ID;
    link.rel = 'stylesheet';
    link.href = './droidwebdisplay-connect-drawer.css?v=0.11.2-connect2';
    document.head.append(link);
  }
  function removeLegacyHeaderText() {
    const eyebrow = document.querySelector('.topbar-brand .eyebrow');
    if (eyebrow?.textContent?.trim().toUpperCase() === 'LOCAL USB BRIDGE') eyebrow.remove();
  }
  function ensureConnectUi() {
    const ui = root();
    if (!ui) return;
    const rail = ui.querySelector('.gb-rail');
    const drawerBody = ui.querySelector('.gb-drawer-body');
    if (!rail || !drawerBody) return;

    let railButton = rail.querySelector('.gb-rail-button[data-group="connect"]');
    if (!railButton) {
      railButton = document.createElement('button');
      railButton.type = 'button';
      railButton.className = 'gb-rail-button';
      railButton.dataset.group = 'connect';
      railButton.setAttribute('aria-selected', 'false');
      railButton.title = 'Connect';
      const icon = document.createElement('span');
      icon.className = 'gb-rail-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.style.setProperty('--gb-icon', 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 24 24\'%3E%3Cg fill=\'none\' stroke=\'black\' stroke-width=\'1.8\' stroke-linecap=\'round\' stroke-linejoin=\'round\'%3E%3Cpath d=\'M8 8V5m8 3V5M7 8h10v4a5 5 0 0 1-5 5v2\'/%3E%3Cpath d=\'M10 19h4\'/%3E%3C/g%3E%3C/svg%3E")');
      const label = document.createElement('span');
      label.className = 'gb-rail-label';
      label.textContent = 'Connect';
      railButton.append(icon, label);
      rail.insertBefore(railButton, rail.querySelector('.gb-rail-spacer'));
    }

    let slot = drawerBody.querySelector('.gb-drawer-slot[data-slot="connect"]');
    if (!slot) {
      const device = document.getElementById('device');
      const refresh = document.getElementById('refresh');
      const connect = document.getElementById('connect');
      const disconnect = document.getElementById('disconnect');
      if (!device || !refresh || !connect || !disconnect) return;

      slot = document.createElement('div');
      slot.className = 'gb-drawer-slot';
      slot.dataset.slot = 'connect';

      const card = document.createElement('section');
      card.className = 'help-card connect-card';
      card.setAttribute('aria-label', 'Android device connection');

      const deviceLabel = document.createElement('label');
      deviceLabel.append(document.createTextNode('Android device'), device);

      const actions = document.createElement('div');
      actions.className = 'button-grid connect-actions';
      actions.append(refresh, connect, disconnect);

      card.append(deviceLabel, actions);
      slot.append(card);
      drawerBody.insertBefore(slot, drawerBody.firstElementChild);
    }
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
    ensureConnectStyles();
    removeLegacyHeaderText();
    ensureConnectUi();
    applyRailOrder();
    ui.querySelectorAll('[data-group]').forEach(button => button.addEventListener('click', () => openGroup(button.dataset.group)));
    ui.querySelector('.gb-drawer-pin')?.addEventListener('click', () => applyPinned(!pinned));
    ui.querySelectorAll('[data-action="close"], .gb-drawer-close').forEach(button => button.addEventListener('click', closeDrawer));
    bindAccordions(); applyPinned(storedPinned(), false); if (pinned) openGroup(storedGroup());
  }
  window.DroidWebDisplayDrawer = { openGroup, closeDrawer, setPinned: value => applyPinned(Boolean(value)) };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
})();