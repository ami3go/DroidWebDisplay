from pathlib import Path

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
