from pathlib import Path

# Web-client layout regression expectations.
p = Path("apps/web-client/tests/layout.test.mjs")
s = p.read_text()
old = '''test("file controls use the accepted production labels", () => {
  for (const label of [">Load<", ">Browse<", ">Download<", ">Reset<"]) assert.match(html, new RegExp(label));
  for (const required of ["Destination folder", "File sync", "Transfer queue"]) assert.match(html, new RegExp(required));
  for (const old of ["Upload selected file(s)", "Automatic two-way folder sync", "PC destination", "data-gate4-check", "data-gate5-check", "data-gate6-check", "data-gate7-check"]) assert.equal(html.includes(old), false);
  assert.match(css, /\\.uniform-buttons > button \\{ min-height: 2\\.55rem; height: 2\\.55rem;/);
  assert.match(css, /#screen \\{ cursor: default; \\}/);
});
'''
new = '''test("file controls use the accepted production labels", () => {
  for (const label of [">Download<", ">Reset<"]) assert.match(html, new RegExp(label));
  for (const required of ["Android File Explorer", "Destination folder", "Custom PC folder", "File sync", "Transfer queue"]) assert.match(html, new RegExp(required));
  for (const old of [">Load<", ">Browse<", "Upload selected file(s)", "Automatic two-way folder sync", "PC destination", "data-gate4-check", "data-gate5-check", "data-gate6-check", "data-gate7-check"]) assert.equal(html.includes(old), false);
  assert.match(css, /\\.uniform-buttons > button \\{ min-height: 2\\.55rem; height: 2\\.55rem;/);
  assert.match(css, /#screen \\{ cursor: default; \\}/);
});
'''
assert old in s
s = s.replace(old, new, 1)
old = '''test("native drawer uses persisted accordions only for multi-section groups", () => {
  assert.match(html, /id="gb-single-drawer-root"/);
  assert.match(html, /data-section-key="files-load"/);
  assert.match(html, /data-section-key="access-web-browser"/);
  assert.equal(mainSource.includes("initializeCollapsibleCards"), false);
  assert.equal(html.includes("card-collapse-button"), false);
});
'''
new = '''test("native drawer uses persisted accordions only for multi-section groups", () => {
  assert.match(html, /id="gb-single-drawer-root"/);
  assert.doesNotMatch(html, /data-section-key="files-load"/);
  assert.match(html, /data-section-key="files-explorer"/);
  assert.match(html, /data-section-key="files-sync"/);
  assert.match(html, /data-section-key="files-queue"/);
  assert.match(html, /data-section-key="access-web-browser"/);
  assert.equal(mainSource.includes("initializeCollapsibleCards"), false);
  assert.equal(html.includes("card-collapse-button"), false);
});
'''
assert old in s
s = s.replace(old, new, 1)
p.write_text(s)

# Phase 9 UX regression expectations: Load/Browse are intentionally removed because
# Android File Explorer now owns both upload and download workflows.
p = Path("tests/ux/test_phase9.py")
s = p.read_text()
old = '''    assert '>Load<' in html
    assert '>Browse<' in html
    assert '>Download<' in html
    assert '>Reset<' in html
    for old in ("Upload selected file(s)", "Browse upload folder", "Download selected", "Reset history", ">Upload<"):
        assert old not in html
'''
new = '''    assert '>Load<' not in html
    assert '>Browse<' not in html
    assert '>Download<' in html
    assert '>Reset<' in html
    assert "Android File Explorer" in html
    assert "Custom PC folder" in html
    for old in ("Upload selected file(s)", "Browse upload folder", "Download selected", "Reset history", ">Upload<"):
        assert old not in html
'''
assert old in s
s = s.replace(old, new, 1)
p.write_text(s)

# Release gate: keep the same UX guarantees but update the contract to the
# Explorer-only transfer design rather than requiring the obsolete Load card.
p = Path("tools/release_gate.py")
s = p.read_text()
old = '''    compact_labels = all(token in html_source for token in (">Load<", ">Browse<", ">Download<", ">Reset<", ">Save<", ">Scan now<")) and ">Upload<" not in html_source
'''
new = '''    compact_labels = all(token in html_source for token in (">Download<", ">Reset<", ">Save<", ">Scan now<")) and all(token not in html_source for token in (">Load<", ">Browse<", ">Upload<")) and "Android File Explorer" in html_source and "Custom PC folder" in html_source
'''
assert old in s
s = s.replace(old, new, 1)
old = '''    native_accordion_contract = all(token in html_source for token in (
        'id="gb-single-drawer-root"', 'data-section-key="files-load"', 'data-section-key="files-sync"',
        'data-section-key="access-web-browser"', 'data-section-key="access-pin"', 'data-section-key="access-revoke-all"',
    )) and "droidwebdisplay.ui.drawer.accordions.v1" in drawer_source
'''
new = '''    native_accordion_contract = all(token in html_source for token in (
        'id="gb-single-drawer-root"', 'data-section-key="files-explorer"', 'data-section-key="files-sync"', 'data-section-key="files-queue"',
        'data-section-key="access-web-browser"', 'data-section-key="access-pin"', 'data-section-key="access-revoke-all"',
    )) and 'data-section-key="files-load"' not in html_source and "droidwebdisplay.ui.drawer.accordions.v1" in drawer_source
'''
assert old in s
s = s.replace(old, new, 1)
p.write_text(s)
