/* DroidWebDisplay Main Single Drawer UI v1.0.0 */
(() => {
  'use strict';

  const VERSION = '1.0.0';
  const PIN_KEY = 'droidwebdisplay.ui.main.singleDrawer.pinned.v1';
  const LAST_GROUP_KEY = 'droidwebdisplay.ui.main.singleDrawer.lastGroup.v1';
  const ACCORDION_KEY = 'droidwebdisplay.ui.main.singleDrawer.accordions.v1';
  const ROOT_ID = 'gb-single-drawer-root';
  const moved = new Map();
  const originalParents = new Set();
  let observer = null;
  let applyScheduled = false;
  let activeGroup = null;
  let pinnedState = null;

  /*
   * Group ownership is ordered only as a tie breaker.  Scoring below gives
   * headings/ids/classes much greater weight than incidental body text so a
   * large parent panel containing the word "Clipboard" no longer swallows
   * unrelated controls.
   */
  const groups = [
    {
      id: 'apps', label: 'Apps', icon: '▦',
      strong: [/running\s+applications?/i, /running\s+apps?/i, /application\s+launcher/i, /app\s+launcher/i],
      weak: [/\bapplications?\b/i, /\bapps?\b/i, /launch\s+app/i, /move\s+app/i]
    },
    {
      id: 'files', label: 'Files', icon: '▤',
      strong: [
        /\bexplorer\b/i, /file\s*transfer/i, /transfer\s*queue/i, /watched\s*folder/i,
        /folder\s*sync/i, /automatic\s+download/i, /auto\s*download/i, /android\s+storage/i,
        /pc\s+download/i, /download\s+folder/i, /upload\s+folder/i, /destination\s+folder/i,
        /external\s+(sd|storage)/i
      ],
      weak: [
        /\bfiles?\b/i, /\bupload/i, /\bdownload/i, /\btransfer/i, /\bfolder/i,
        /\bstorage\b/i, /\bdirectory\b/i, /\bpath\b/i, /\bqueue\b/i, /\bretry\b/i
      ]
    },
    {
      id: 'clipboard', label: 'Clipboard', icon: '▣',
      strong: [/\bclipboard\b/i, /clipboard\s*sync/i, /remote\s*copy/i, /explicit\s*paste/i],
      weak: [/\bpaste\b/i, /copy\s+to\s+(android|phone)/i, /copy\s+from\s+(android|phone)/i]
    },
    {
      id: 'display', label: 'Display', icon: '▱',
      strong: [/display\s*mode/i, /virtual\s*display/i, /physical\s*(display|screen)/i, /virtual\s*keyboard/i, /ime\s*policy/i],
      weak: [/\bresolution\b/i, /\bdpi\b/i, /\bdensity\b/i, /\bfullscreen\b/i, /\brotation\b/i, /size\s*mode/i]
    },
    {
      id: 'audio', label: 'Audio', icon: '◖',
      strong: [/\baudio\b/i, /audio\s*(capture|pipeline|settings?)/i, /\bopus\b/i],
      weak: [/\bmute\b/i, /\bvolume\b/i, /speaker/i, /sound/i]
    },
    {
      id: 'access', label: 'Access', icon: '⌂',
      strong: [/pc[-\s]*local\s*access/i, /local\s*access/i, /trusted\s*browser/i, /trust\s*duration/i, /session\s*trust/i],
      weak: [/trusted\s*session/i, /trust\s*choice/i, /remember\s*this\s*browser/i, /browser[-\s]*session/i, /1[-\s]*(hour|day|week|month|year)/i, /forever/i, /custom/i]
    },
    {
      id: 'network', label: 'Network', icon: '◎',
      strong: [/network\s*(access|settings?)/i, /\blan\b/i, /security\s*policy/i, /host\s*validation/i, /client\s*allowlist/i],
      weak: [/bind\s*address/i, /https/i, /certificate/i, /origin/i, /allowlist/i, /firewall/i, /specific\s*interface/i]
    },
    {
      id: 'diagnostics', label: 'Diagnostics', icon: '⌁',
      strong: [/diagnostic/i, /troubleshoot/i, /connection\s+details/i, /debug\s*(log|info)/i, /mode\s*statistic/i],
      weak: [/\blogs?\b/i, /evidence/i, /health/i, /status\s+details/i, /statistic/i]
    },
    {
      id: 'settings', label: 'Settings', icon: '⚙',
      strong: [/\bsettings?\b/i, /preferences?/i, /configuration/i],
      weak: [/import\s+settings/i, /export\s+settings/i, /defaults?/i]
    }
  ];

  const primarySelectors = [
    '[class*="card" i]', '[class*="panel" i]', '[class*="tile" i]',
    'section', 'details', 'fieldset', '[role="group"]'
  ];
  const rowSelectors = [
    '[class*="setting-row" i]', '[class*="settings-row" i]',
    '[class*="setting-group" i]', '[class*="settings-group" i]',
    '[class*="form-row" i]', '[class*="field-row" i]',
    '[class*="field-group" i]', '[class*="control-row" i]',
    '[class*="control-group" i]'
  ];
  const allSelectors = [...primarySelectors, ...rowSelectors];


  function queryPin() {
    const v = new URLSearchParams(location.search).get('pin');
    if (v === '1' || v === 'true' || v === 'yes') return true;
    if (v === '0' || v === 'false' || v === 'no') return false;
    return null;
  }


  function isPinned() {
    if (pinnedState !== null) return pinnedState;
    const q = queryPin();
    if (q !== null) return q;
    try { return localStorage.getItem(PIN_KEY) === '1'; } catch (_) { return false; }
  }


  function savePinned(value) {
    try { localStorage.setItem(PIN_KEY, value ? '1' : '0'); } catch (_) {}
  }

  function saveLastGroup(id) {
    try { localStorage.setItem(LAST_GROUP_KEY, id); } catch (_) {}
  }

  function getLastGroup() {
    try {
      const id = localStorage.getItem(LAST_GROUP_KEY);
      return groups.some(g => g.id === id) ? id : null;
    } catch (_) { return null; }
  }


  function loadAccordionState() {
    try {
      return JSON.parse(localStorage.getItem(ACCORDION_KEY) || '{}') || {};
    } catch (_) { return {}; }
  }

  function saveAccordionState(state) {
    try { localStorage.setItem(ACCORDION_KEY, JSON.stringify(state || {})); } catch (_) {}
  }

  function sectionKey(gid, title, ordinal) {
    return `${gid}::${String(title || '').trim().toLowerCase()}::${ordinal}`;
  }

  function defaultSectionOpen(gid, ordinal) {
    return ordinal < (gid === 'files' || gid === 'diagnostics' ? 2 : 1);
  }

  function visibleText(el, limit = 1200) {
    return (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, limit);
  }

  function directHeadingText(el) {
    const selectors = [
      ':scope > h1', ':scope > h2', ':scope > h3', ':scope > h4', ':scope > h5', ':scope > h6',
      ':scope > legend', ':scope > summary', ':scope > [class*="title" i]', ':scope > [class*="header" i]'
    ];
    for (const selector of selectors) {
      try {
        const h = el.querySelector(selector);
        const t = visibleText(h, 220);
        if (t) return t;
      } catch (_) {}
    }
    return '';
  }

  function ownIdentityText(el) {
    const attrs = [
      el.id, el.getAttribute?.('aria-label'), el.getAttribute?.('title'), el.getAttribute?.('name'),
      el.getAttribute?.('data-section'), el.getAttribute?.('data-testid'), el.getAttribute?.('data-card'),
      String(el.className || '')
    ].filter(Boolean).join(' ');
    return `${directHeadingText(el)} ${attrs}`.replace(/\s+/g, ' ').trim().slice(0, 900);
  }

  function directLabelText(el) {
    const parts = [];
    try {
      el.querySelectorAll(':scope > label, :scope > span, :scope > strong, :scope > b').forEach(n => {
        const t = visibleText(n, 120);
        if (t) parts.push(t);
      });
    } catch (_) {}
    return parts.join(' ').slice(0, 360);
  }

  function scoreGroup(el, g) {
    const identity = `${ownIdentityText(el)} ${directLabelText(el)}`;
    const body = visibleText(el, 850);
    let score = 0;
    for (const rx of g.strong) {
      if (rx.test(identity)) score += 18;
      else if (rx.test(body)) score += 7;
    }
    for (const rx of g.weak) {
      if (rx.test(identity)) score += 8;
      else if (rx.test(body)) score += 2;
    }
    return score;
  }

  function classification(el) {
    // Never absorb the real video/canvas surface.
    const body = visibleText(el, 900);
    if (/android\s+display/i.test(body) && el.querySelector?.('canvas,video')) {
      return { group: null, score: 0, runnerUp: 0, scores: {} };
    }
    const scores = {};
    for (const g of groups) scores[g.id] = scoreGroup(el, g);
    const ordered = Object.entries(scores).sort((a, b) => b[1] - a[1]);
    const [bestId, bestScore] = ordered[0] || [null, 0];
    const runnerUp = ordered[1]?.[1] || 0;
    // Require a meaningful signal.  A strong identity hit is normally >= 18;
    // body-only hits can still classify a compact row/card at >= 7.
    const compact = el.querySelectorAll?.('button,input,select,textarea,a').length <= 8 && body.length <= 1200;
    const threshold = compact ? 6 : 10;
    return { group: bestScore >= threshold ? bestId : null, score: bestScore, runnerUp, scores };
  }

  function groupFor(el) { return classification(el).group; }

  function looksLikeUnit(el) {
    if (!(el instanceof HTMLElement)) return false;
    if (el.closest('#' + ROOT_ID)) return false;
    if (['SCRIPT','STYLE','LINK','HTML','BODY','MAIN','FORM','CANVAS','VIDEO','NAV','HEADER','FOOTER'].includes(el.tagName)) return false;
    const controls = el.querySelectorAll('button,input,select,textarea,a').length;
    const text = visibleText(el, 2200);
    if (!text || text.length > 2100 || controls > 30) return false;
    const cls = String(el.className || '');
    const semantic = /card|panel|tile|setting-row|settings-row|setting-group|settings-group|form-row|field-row|field-group|control-row|control-group/i.test(cls)
      || ['SECTION','DETAILS','FIELDSET'].includes(el.tagName)
      || el.getAttribute('role') === 'group';
    const hasDirectHeading = !!directHeadingText(el);
    return semantic || hasDirectHeading;
  }

  function nestedClassifiedUnits(el) {
    const descendants = [...el.querySelectorAll(allSelectors.join(','))]
      .filter(child => child !== el && looksLikeUnit(child))
      .map(child => ({ el: child, c: classification(child) }))
      .filter(x => x.c.group);
    return descendants;
  }

  function isCompositeContainer(el) {
    const nested = nestedClassifiedUnits(el);
    if (nested.length < 2) return false;
    const distinct = new Set(nested.map(x => x.c.group));
    // Two or more independently classified nested groups mean this is a
    // layout container, not a card to be moved as a whole.
    if (distinct.size >= 2) return true;
    // A generic parent with several classified rows should still yield to
    // its more precise children.
    return !directHeadingText(el) && nested.length >= 2;
  }

  function candidateUnits() {
    const all = [...document.querySelectorAll(allSelectors.join(','))]
      .filter(looksLikeUnit)
      .map(el => ({ el, c: classification(el) }))
      .filter(x => x.c.group)
      .filter(x => !isCompositeContainer(x.el));

    // Prefer a coherent card over its child rows when all agree on one group;
    // prefer child rows when the ancestor is mixed/ambiguous.
    return all.filter(item => {
      const ancestors = all.filter(other => other !== item && other.el.contains(item.el));
      for (const parent of ancestors) {
        if (parent.c.group === item.c.group && parent.c.score >= item.c.score && !isCompositeContainer(parent.el)) {
          return false;
        }
      }
      const children = all.filter(other => other !== item && item.el.contains(other.el));
      if (children.some(child => child.c.group !== item.c.group)) return false;
      return true;
    }).map(x => x.el);
  }


  function deriveSectionTitle(el, gid, ordinal) {
    const heading = directHeadingText(el) || directLabelText(el);
    if (heading) return heading.replace(/\s+/g, ' ').trim().slice(0, 80);
    const firstStrong = groups.find(g => g.id === gid)?.label || 'Section';
    const t = visibleText(el, 80).replace(/\s+/g, ' ').trim();
    return t ? t : `${firstStrong} ${ordinal + 1}`;
  }

  function createAccordionWrapper(unit, gid, ordinal) {
    const title = deriveSectionTitle(unit, gid, ordinal);
    const state = loadAccordionState();
    const key = sectionKey(gid, title, ordinal);
    const details = document.createElement('details');
    details.className = 'gb-accordion';
    details.dataset.sectionKey = key;
    details.dataset.group = gid;
    details.dataset.title = title;
    const open = Object.prototype.hasOwnProperty.call(state, key) ? Boolean(state[key]) : defaultSectionOpen(gid, ordinal);
    details.open = open;
    const summary = document.createElement('summary');
    summary.className = 'gb-accordion-summary';
    const triangle = document.createElement('span');
    triangle.className = 'gb-accordion-triangle';
    triangle.setAttribute('aria-hidden', 'true');
    triangle.textContent = '▸';
    const label = document.createElement('span');
    label.className = 'gb-accordion-label';
    label.textContent = title;
    summary.append(triangle, label);
    details.appendChild(summary);
    details.addEventListener('toggle', () => {
      const current = loadAccordionState();
      current[key] = details.open;
      saveAccordionState(current);
    });
    details.appendChild(unit);
    return { details, key, title };
  }

  function makeEmptyState(g) {
    return `<div class="gb-drawer-empty" data-empty-for="${g.id}"><strong>${g.label}</strong><span>No matching controls were found in this build.</span></div>`;
  }


  const FOCUS_WORDS = /\bfocus\b/i;
  const REMOVED_LAYOUT_WORDS = /\b(auto|compact|focus)\b/i;
  const LAYOUT_CONTEXT = /\b(screen|layout|workspace|view)\s*(mode|layout)?\b/i;
  let focusEnforcementScheduled = false;

  function textOf(el, limit = 300) {
    return visibleText(el, limit).replace(/\s+/g, ' ').trim();
  }

  function closestControlContainer(el) {
    if (!el) return null;
    return el.closest?.('label,[class*="field" i],[class*="control" i],[class*="setting" i],[class*="mode" i],[role="group"],fieldset') || el.parentElement;
  }

  function looksLikeLayoutModeControl(el) {
    if (!(el instanceof HTMLElement)) return false;
    const own = [
      el.id, el.getAttribute('name'), el.getAttribute('aria-label'), el.getAttribute('title'),
      String(el.className || ''), textOf(closestControlContainer(el), 500)
    ].filter(Boolean).join(' ');
    if (!LAYOUT_CONTEXT.test(own)) return false;
    const options = el.tagName === 'SELECT'
      ? [...el.options].map(o => o.textContent || o.value).join(' ')
      : own;
    return FOCUS_WORDS.test(options) && /\b(auto|compact)\b/i.test(options);
  }

  function activateFocusControl(el) {
    try {
      if (el.tagName === 'SELECT') {
        const option = [...el.options].find(o => FOCUS_WORDS.test(`${o.textContent || ''} ${o.value || ''}`));
        if (!option) return false;
        if (el.value !== option.value) {
          el.value = option.value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return true;
      }
      if (el.matches('input[type="radio"],input[type="checkbox"]')) {
        const label = closestControlContainer(el);
        if (!FOCUS_WORDS.test(`${el.value || ''} ${textOf(label, 200)}`)) return false;
        if (!el.checked) {
          el.click();
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
        return true;
      }
      if (el.matches('button,[role="button"]') && FOCUS_WORDS.test(textOf(el, 120))) {
        const pressed = el.getAttribute('aria-pressed');
        const selected = el.getAttribute('aria-selected');
        if (pressed !== 'true' && selected !== 'true') el.click();
        return true;
      }
    } catch (_) {}
    return false;
  }

  function hideLayoutModeContainer(el) {
    const container = closestControlContainer(el);
    if (!container || container.closest('#' + ROOT_ID)) return;
    container.dataset.gbRemovedLayoutMode = 'true';
    container.style.display = 'none';
  }

  function removeLegacyLayoutModes() {
    let activated = false;
    document.querySelectorAll('select').forEach(el => {
      if (!looksLikeLayoutModeControl(el)) return;
      activated = activateFocusControl(el) || activated;
      hideLayoutModeContainer(el);
    });

    const candidates = [...document.querySelectorAll('input[type="radio"],button,[role="button"]')];
    const grouped = new Map();
    for (const el of candidates) {
      const container = closestControlContainer(el);
      if (!container || container.closest('#' + ROOT_ID)) continue;
      const context = `${textOf(container, 500)} ${String(container.className || '')} ${container.id || ''}`;
      if (!LAYOUT_CONTEXT.test(context) || !REMOVED_LAYOUT_WORDS.test(context)) continue;
      if (!/\bfocus\b/i.test(context) || !/\b(auto|compact)\b/i.test(context)) continue;
      if (!grouped.has(container)) grouped.set(container, []);
      grouped.get(container).push(el);
    }
    for (const [container, controls] of grouped) {
      const focus = controls.find(el => FOCUS_WORDS.test(`${el.value || ''} ${textOf(el, 120)} ${textOf(closestControlContainer(el), 160)}`));
      if (focus) activated = activateFocusControl(focus) || activated;
      container.dataset.gbRemovedLayoutMode = 'true';
      container.style.display = 'none';
    }
    document.documentElement.dataset.gbMainLayout = 'focus';
    document.documentElement.classList.add('gb-focus-only-layout');
    return activated;
  }

  function enforceFocusOnlyLayout() {
    if (focusEnforcementScheduled) return;
    focusEnforcementScheduled = true;
    queueMicrotask(() => {
      focusEnforcementScheduled = false;
      removeLegacyLayoutModes();
    });
  }

  function makeUI() {
    if (document.getElementById(ROOT_ID)) return document.getElementById(ROOT_ID);
    const root = document.createElement('div');
    root.id = ROOT_ID;
    root.dataset.version = VERSION;
    root.innerHTML = `
      <nav class="gb-rail" aria-label="DroidWebDisplay tools">
        ${groups.map(g => `<button type="button" class="gb-rail-button" data-group="${g.id}" aria-selected="false" title="${g.label}"><span class="gb-rail-icon">${g.icon}</span><span class="gb-rail-label">${g.label}</span></button>`).join('')}
        <div class="gb-rail-spacer"></div>
      </nav>
      <aside class="gb-drawer" aria-hidden="true">
        <div class="gb-drawer-header">
          <div class="gb-drawer-title">Tools</div>
          <button type="button" class="gb-drawer-pin" data-action="pin" aria-pressed="false" title="Pin drawer"><span aria-hidden="true">📌</span><span class="gb-pin-text">Pin</span></button>
          <button type="button" class="gb-drawer-close" aria-label="Close drawer" title="Close drawer">×</button>
        </div>
        <div class="gb-drawer-body">${groups.map(g => `<div class="gb-drawer-slot" data-slot="${g.id}">${makeEmptyState(g)}</div>`).join('')}</div>
        <div class="gb-drawer-footer"><button type="button" class="gb-drawer-action" data-action="close">Close</button></div>
      </aside>`;
    document.body.appendChild(root);
    root.querySelectorAll('[data-group]').forEach(btn => btn.addEventListener('click', () => openGroup(btn.dataset.group)));
    root.querySelectorAll('[data-action="close"],.gb-drawer-close').forEach(btn => btn.addEventListener('click', closeDrawer));
    root.querySelector('[data-action="pin"]')?.addEventListener('click', togglePinned);
    applyPinState(isPinned(), false);
    return root;
  }

  function findWorkspace() {
    const parents = [...originalParents].filter(p => p && p.isConnected);
    if (parents.length < 1) return null;
    let a = parents[0];
    while (a && a !== document.body) {
      if (parents.every(p => a.contains(p))) return a;
      a = a.parentElement;
    }
    return null;
  }

  function mountCards() {
    const root = makeUI();
    const units = candidateUnits();
    let count = 0;
    const groupOrdinals = Object.fromEntries(groups.map(g => [g.id, 0]));
    for (const unit of units) {
      if (moved.has(unit)) continue;
      const gid = groupFor(unit);
      if (!gid) continue;
      const slot = root.querySelector(`[data-slot="${gid}"]`);
      if (!slot) continue;
      const parent = unit.parentElement;
      if (!parent || parent.closest('#' + ROOT_ID)) continue;
      const placeholder = document.createComment(`gb-single-drawer:${gid}`);
      parent.insertBefore(placeholder, unit);
      const ordinal = groupOrdinals[gid] || 0;
      groupOrdinals[gid] = ordinal + 1;
      const wrapped = createAccordionWrapper(unit, gid, ordinal);
      moved.set(unit, { parent, placeholder, gid, wrapper: wrapped.details, sectionKey: wrapped.key, title: wrapped.title });
      originalParents.add(parent);
      slot.appendChild(wrapped.details);
      unit.dataset.gbDrawerGroup = gid;
      count++;
    }

    for (const parent of originalParents) {
      if (!parent?.isConnected) continue;
      const meaningful = [...parent.children].some(ch => ch.id !== ROOT_ID && visibleText(ch).length > 0);
      if (!meaningful) parent.classList.add('gb-empty-side-panel');
    }
    const workspace = findWorkspace();
    if (workspace && workspace !== document.body && workspace !== document.documentElement) workspace.classList.add('gb-single-drawer-workspace');
    updateButtonAvailability();
    return count;
  }

  function restoreCards() {
    if (observer) { observer.disconnect(); observer = null; }
    for (const [unit, info] of moved.entries()) {
      try {
        if (info.placeholder?.parentNode) info.placeholder.parentNode.insertBefore(unit, info.placeholder);
        else if (info.parent?.isConnected) info.parent.appendChild(unit);
        info.wrapper?.remove();
        info.placeholder?.remove();
        delete unit.dataset.gbDrawerGroup;
      } catch (_) {}
    }
    moved.clear();
    originalParents.clear();
    document.querySelectorAll('.gb-empty-side-panel').forEach(el => el.classList.remove('gb-empty-side-panel'));
    document.querySelectorAll('.gb-single-drawer-workspace').forEach(el => el.classList.remove('gb-single-drawer-workspace'));
    document.documentElement.classList.remove('gb-single-drawer-enabled', 'gb-single-drawer-pinned');
    document.getElementById(ROOT_ID)?.remove();
    activeGroup = null;
  }

  function updateButtonAvailability() {
    const root = document.getElementById(ROOT_ID);
    if (!root) return;
    for (const g of groups) {
      const slot = root.querySelector(`[data-slot="${g.id}"]`);
      const movedChildren = [...(slot?.children || [])].filter(ch => !ch.classList.contains('gb-drawer-empty'));
      const has = movedChildren.length > 0;
      slot?.querySelector(`[data-empty-for="${g.id}"]`)?.classList.toggle('gb-hidden', has);
      const btn = root.querySelector(`[data-group="${g.id}"]`);
      if (btn) {
        // All icons deliberately stay active/clickable.  Empty sections show a
        // diagnostic empty state instead of becoming disabled.
        btn.disabled = false;
        btn.classList.toggle('gb-has-content', has);
        btn.dataset.itemCount = String(movedChildren.length);
      }
    }
  }

  function applyPinState(pinned, persist = true) {
    pinnedState = Boolean(pinned);
    const root = document.getElementById(ROOT_ID);
    if (persist) savePinned(pinnedState);
    document.documentElement.classList.toggle('gb-single-drawer-pinned', pinnedState);
    if (!root) return;
    root.classList.toggle('gb-pinned', pinnedState);
    const pin = root.querySelector('.gb-drawer-pin');
    if (pin) {
      pin.setAttribute('aria-pressed', pinnedState ? 'true' : 'false');
      pin.title = pinnedState ? 'Unpin drawer' : 'Pin drawer';
      const text = pin.querySelector('.gb-pin-text');
      if (text) text.textContent = pinnedState ? 'Pinned' : 'Pin';
    }
    if (pinnedState) {
      const id = activeGroup || getLastGroup() || groups[0].id;
      openGroup(id, { fromPin: true });
    }
  }

  function togglePinned() { applyPinState(!isPinned()); }

  function openGroup(id, _options = {}) {
    const root = document.getElementById(ROOT_ID);
    if (!root || !groups.some(g => g.id === id)) return;
    activeGroup = id;
    saveLastGroup(id);
    root.querySelectorAll('.gb-drawer-slot').forEach(s => s.classList.toggle('gb-active', s.dataset.slot === id));
    root.querySelectorAll('[data-group]').forEach(b => b.setAttribute('aria-selected', b.dataset.group === id ? 'true' : 'false'));
    const g = groups.find(x => x.id === id);
    root.querySelector('.gb-drawer-title').textContent = g?.label || 'Tools';
    const drawer = root.querySelector('.gb-drawer');
    drawer.classList.add('gb-open');
    drawer.setAttribute('aria-hidden', 'false');
  }

  function closeDrawer() {
    const root = document.getElementById(ROOT_ID);
    if (!root) return;
    // A pinned drawer is intentionally fixed.  Unpin first if the user wants
    // to close it; this prevents accidental collapse while working in Files.
    if (isPinned()) return;
    root.querySelector('.gb-drawer')?.classList.remove('gb-open');
    root.querySelector('.gb-drawer')?.setAttribute('aria-hidden', 'true');
    root.querySelectorAll('[data-group]').forEach(b => b.setAttribute('aria-selected', 'false'));
    activeGroup = null;
  }



  function enableDrawer() {
    enforceFocusOnlyLayout();
    document.documentElement.classList.add('gb-single-drawer-enabled');
    makeUI();
    mountCards();
    observe();
    applyPinState(isPinned(), false);
    if (isPinned()) openGroup(getLastGroup() || groups[0].id);
  }


  function diagnostics() {
    const candidates = [...document.querySelectorAll(allSelectors.join(','))]
      .filter(looksLikeUnit)
      .map(el => {
        const c = classification(el);
        return {
          heading: directHeadingText(el),
          identity: ownIdentityText(el),
          text: visibleText(el, 260),
          group: c.group,
          score: c.score,
          runnerUp: c.runnerUp,
          scores: c.scores,
          composite: isCompositeContainer(el),
          tag: el.tagName,
          className: String(el.className || ''),
          moved: moved.has(el),
          movedInfo: moved.has(el) ? moved.get(el) : null
        };
      });
    const counts = Object.fromEntries(groups.map(g => [g.id, [...moved.values()].filter(v => v.gid === g.id).length]));
    return {
      version: VERSION,
      mode: 'focus-only',
      pinned: isPinned(),
      activeGroup,
      moved: moved.size,
      counts,
      candidates
    };
  }

  window.DroidWebDisplaySingleDrawerLab = {
    version: VERSION,
    setPinned: value => applyPinState(Boolean(value)),
    enforceFocusOnlyLayout,
    openGroup,
    diagnostics,
    remount: mountCards
  };

  function boot() {
    enforceFocusOnlyLayout();
    enableDrawer();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
