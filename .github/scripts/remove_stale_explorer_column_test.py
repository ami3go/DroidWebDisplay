from pathlib import Path

path = Path('apps/web-client/tests/connect-drawer.test.mjs')
text = path.read_text(encoding='utf-8')
old = '''test("Android File Explorer columns are user resizable", () => {\n  assert.match(drawerSource, /EXPLORER_COLUMNS_KEY = 'droidwebdisplay\\.ui\\.explorer\\.columns\\.v1'/);\n  assert.match(drawerSource, /function bindExplorerColumnResize\\(\\)/);\n  assert.match(drawerSource, /explorer-column-resizer/);\n  assert.match(drawerSource, /name-size/);\n  assert.match(drawerSource, /size-modified/);\n  assert.match(drawerSource, /addEventListener\\('pointermove'/);\n  assert.match(drawerSource, /localStorage\\.removeItem\\(EXPLORER_COLUMNS_KEY\\)/);\n  assert.match(drawerCss, /--dwd-explorer-size-w/);\n  assert.match(drawerCss, /--dwd-explorer-modified-w/);\n  assert.match(drawerCss, /cursor: col-resize/);\n});\n'''
if old not in text:
    raise SystemExit('stale Explorer column-resize test not found')
path.write_text(text.replace(old, '', 1), encoding='utf-8')
