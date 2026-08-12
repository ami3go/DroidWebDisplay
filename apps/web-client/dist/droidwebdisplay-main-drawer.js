/* DroidWebDisplay native single-drawer controller v1.2.2 */
(() => {
  'use strict';
  const PIN_KEY = 'droidwebdisplay.ui.drawer.pinned.v1';
  const LAST_GROUP_KEY = 'droidwebdisplay.ui.drawer.lastGroup.v1';
  const ACCORDION_KEY = 'droidwebdisplay.ui.drawer.accordions.v1';
  const ROOT_ID = 'gb-single-drawer-root';
  const GROUPS = ['display','clipboard','files','apps','audio','access','network','diagnostics','settings'];
  let activeGroup = null;
  let pinned = false;
  let latencyTimer = null;
  const root = () => document.getElementById(ROOT_ID);
  const drawer = () => root()?.querySelector('.gb-drawer');
  function get(key, fallback = null) { try { return localStorage.getItem(key) ?? fallback; } catch (_) { return fallback; } }
  function set(key, value) { try { localStorage.setItem(key, value); } catch (_) {} }
  function storedPinned() { return get(PIN_KEY, '0') === '1'; }
  function storedGroup() { const value = get(LAST_GROUP_KEY, 'display'); return GROUPS.includes(value) ? value : 'display'; }
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
    // Loading the Display drawer uses cached tuning only. Android media codec
    // diagnostics run only after the user explicitly presses Probe encoders.
    if (group === 'display') void refreshEncoderUi(false);
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
  async function csrfToken() {
    const response = await fetch('/api/v1/auth/status', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Authentication status failed (${response.status})`);
    const value = await response.json();
    if (!value.csrfToken) throw new Error('Authenticated CSRF token is unavailable');
    return value.csrfToken;
  }
  async function requestJson(url, options = {}) {
    const headers = new Headers(options.headers || {});
    if (options.body !== undefined) headers.set('Content-Type', 'application/json');
    const method = String(options.method || 'GET').toUpperCase();
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) headers.set('X-DroidWebDisplay-CSRF', await csrfToken());
    const response = await fetch(url, { ...options, headers, cache: 'no-store' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || payload?.error?.message || `Request failed (${response.status})`);
    return payload;
  }
  function selectedSerial() { return document.getElementById('device')?.value || ''; }
  function setEncoderStatus(text, error = false) {
    const status = document.getElementById('latency-encoder-status');
    if (!status) return;
    status.textContent = text;
    status.classList.toggle('error-text', error);
  }
  function installLatencyControls() {
    const card = root()?.querySelector('.gb-drawer-slot[data-slot="display"] .display-mode-card');
    if (!card || document.getElementById('latency-video-encoder')) return;
    const panel = document.createElement('div');
    panel.className = 'latency-tuning-panel';
    panel.innerHTML = `
      <hr>
      <h3>Responsiveness</h3>
      <label>Video encoder
        <select id="latency-video-encoder"><option value="">Auto (scrcpy chooses encoder)</option></select>
      </label>
      <div class="two-button-row uniform-buttons">
        <button id="latency-encoder-refresh" type="button" class="secondary">Probe encoders</button>
        <button id="latency-encoder-benchmark" type="button" class="secondary">Compatibility test</button>
      </div>
      <p id="latency-encoder-status" class="running-app-status">Auto mode leaves encoder selection to scrcpy until you choose one explicitly.</p>
      <p class="virtual-keyboard-note">Probe runs Android codec diagnostics only when requested. Compatibility test briefly starts candidate H.264 encoders; startup time is not treated as interactive latency.</p>`;
    card.append(panel);
    document.getElementById('latency-encoder-refresh')?.addEventListener('click', () => void refreshEncoderUi(true));
    document.getElementById('latency-encoder-benchmark')?.addEventListener('click', () => void testEncoderCompatibility());
    document.getElementById('latency-video-encoder')?.addEventListener('change', () => void saveEncoderPreference());
    document.getElementById('device')?.addEventListener('change', () => {
      if (activeGroup === 'display') void refreshEncoderUi(false);
    });
  }
  async function refreshEncoderUi(probe = false) {
    const serial = selectedSerial();
    const select = document.getElementById('latency-video-encoder');
    if (!select) return;
    if (!serial) {
      select.innerHTML = '<option value="">Auto (scrcpy chooses encoder)</option>';
      setEncoderStatus('Select an authorized Android device. Probe is manual.');
      return;
    }
    if (probe) setEncoderStatus('Probing Android H.264 encoders…');
    try {
      const suffix = probe ? '?probe=true' : '';
      const data = await requestJson(`/api/v1/devices/${encodeURIComponent(serial)}/video-encoders${suffix}`);
      const previous = data.preference || '';
      select.replaceChildren();
      const auto = document.createElement('option'); auto.value = ''; auto.textContent = 'Auto (scrcpy chooses encoder)'; select.append(auto);
      for (const encoder of data.encoders || []) {
        const option = document.createElement('option'); option.value = encoder; option.textContent = encoder; select.append(option);
      }
      if (previous && ![...select.options].some(option => option.value === previous)) {
        const option = document.createElement('option'); option.value = previous; option.textContent = `${previous} (saved)`; select.append(option);
      }
      select.value = previous;
      const compatible = Array.isArray(data.compatibleEncoders) ? data.compatibleEncoders : [];
      const compatibilityText = compatible.length ? ` · ${compatible.length} compatibility-tested` : '';
      const invalidationText = data.lastInvalidation ? ` · previous tuning cleared: ${data.lastInvalidation}` : '';
      setEncoderStatus(previous
        ? `Selected: ${previous}${compatibilityText}${invalidationText}`
        : `Auto: scrcpy chooses encoder${compatibilityText}${invalidationText}`);
    } catch (error) {
      setEncoderStatus(`Encoder information failed: ${error instanceof Error ? error.message : String(error)}`, true);
    }
  }
  async function saveEncoderPreference() {
    const serial = selectedSerial();
    const select = document.getElementById('latency-video-encoder');
    if (!serial || !select) return;
    setEncoderStatus('Saving encoder preference…');
    try {
      const data = await requestJson(`/api/v1/devices/${encodeURIComponent(serial)}/video-encoder`, {
        method: 'PUT', body: JSON.stringify({ encoder: select.value || null }),
      });
      setEncoderStatus(data.preference ? `Selected: ${data.preference}` : 'Auto: scrcpy chooses encoder.');
    } catch (error) {
      setEncoderStatus(`Unable to save encoder: ${error instanceof Error ? error.message : String(error)}`, true);
    }
  }
  async function testEncoderCompatibility() {
    const serial = selectedSerial();
    if (!serial) { setEncoderStatus('Select an Android device first.', true); return; }
    const disconnect = document.getElementById('disconnect');
    if (disconnect && !disconnect.disabled) { setEncoderStatus('Disconnect the active display before testing encoders.', true); return; }
    const button = document.getElementById('latency-encoder-benchmark');
    if (button) button.disabled = true;
    setEncoderStatus('Testing H.264 encoder compatibility… this may take several seconds.');
    try {
      const data = await requestJson(`/api/v1/devices/${encodeURIComponent(serial)}/video-encoders/compatibility`, {
        method: 'POST', body: JSON.stringify({ encoders: [] }),
      });
      const checks = data.compatibilityChecks || data.benchmarks || [];
      const details = checks.map(item => item.success ? `${item.encoder} compatible` : `${item.encoder} failed`).join(' · ');
      setEncoderStatus(`${data.compatibleEncoders?.length || 0} compatible${details ? ` · ${details}` : ''}. Auto still uses scrcpy selection.`);
      await refreshEncoderUi(false);
    } catch (error) {
      setEncoderStatus(`Compatibility test failed: ${error instanceof Error ? error.message : String(error)}`, true);
    } finally {
      if (button) button.disabled = false;
    }
  }
  function installLatencyHud() {
    const statistics = document.getElementById('statistics');
    if (!statistics || document.getElementById('latency-hud')) return;
    const hud = document.createElement('div');
    hud.id = 'latency-hud';
    hud.className = 'statistics latency-hud';
    hud.textContent = 'Latency metrics waiting for an active video session.';
    statistics.insertAdjacentElement('afterend', hud);
    let previous = '';
    const update = () => {
      const m = window.__dwdLatencyMetrics || {};
      if (!Object.keys(m).length) return;
      const fps = Number(m.videoFps || 0).toFixed(1);
      const wsQueueDelay = Number(m.videoSocketQueueDelayMs || 0).toFixed(1);
      const wsQueued = (Number(m.videoSocketQueuedBytes || 0) / 1024).toFixed(1);
      const parserToDraw = Number(m.parserToDrawMs || 0).toFixed(1);
      const decode = Number(m.decodeLatencyMs || 0).toFixed(1);
      const present = Number(m.presentationLatencyMs || 0).toFixed(1);
      const queue = Number(m.decoderQueue || 0);
      const pending = Number(m.controlPendingWrites || 0);
      const controlQueue = Number(m.controlQueueDelayMs || 0).toFixed(1);
      const buffered = (Number(m.controlSocketBufferedBytes || 0) / 1024).toFixed(1);
      const coalesced = Number(m.controlMovesCoalesced || 0);
      const recoveries = Number(m.decoderRecoveries || 0);
      const overflows = Number(m.videoSocketBacklogOverflows || 0);
      const workerRestarts = Number(m.videoWorkerRestarts || 0);
      const backend = m.rendererBackend || 'canvas2d';
      const text = `Low latency · ${fps} fps · WS queue ${wsQueueDelay} ms / ${wsQueued} KiB · parser→draw ${parserToDraw} ms · decode ${decode} ms · present ${present} ms · decoder q ${queue} · control q ${controlQueue} ms / pending ${pending} · send buffer ${buffered} KiB · moves coalesced ${coalesced} · decoder recoveries ${recoveries} · WS overflows ${overflows} · worker restarts ${workerRestarts} · ${backend}`;
      if (text !== previous) { hud.textContent = text; previous = text; }
    };
    if (latencyTimer !== null) window.clearInterval(latencyTimer);
    latencyTimer = window.setInterval(update, 250);
  }
  function boot() {
    const ui = root(); if (!ui) return;
    document.documentElement.classList.add('gb-single-drawer-enabled');
    applyRailOrder();
    ui.querySelectorAll('[data-group]').forEach(button => button.addEventListener('click', () => openGroup(button.dataset.group)));
    ui.querySelector('.gb-drawer-pin')?.addEventListener('click', () => applyPinned(!pinned));
    ui.querySelectorAll('[data-action="close"], .gb-drawer-close').forEach(button => button.addEventListener('click', closeDrawer));
    bindAccordions();
    installLatencyControls();
    installLatencyHud();
    applyPinned(storedPinned(), false); if (pinned) openGroup(storedGroup());
  }
  window.DroidWebDisplayDrawer = { openGroup, closeDrawer, setPinned: value => applyPinned(Boolean(value)) };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true }); else boot();
})();
