#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps/web-client"


def replace_once_text(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(replace_once_text(text, old, new, label), encoding="utf-8")


def phase5() -> None:
    path = WEB / "src/transfer-controller.ts"
    text = path.read_text(encoding="utf-8")

    old_handlers = '''    this.elements.storageBody.addEventListener("click", (event) => {
      if (event.target === this.elements.storageBody) this.clearSelection();
    });
    this.elements.storageBody.addEventListener("contextmenu", (event) => {
      if (event.target !== this.elements.storageBody) return;
      event.preventDefault();
      this.showContextMenu(event.clientX, event.clientY, null);
    });
'''
    new_handlers = '''    this.elements.storageBody.addEventListener("click", (event) => {
      const target = event.target as Element | null;
      if (event.target === this.elements.storageBody) {
        this.clearSelection();
        return;
      }
      const row = target?.closest<HTMLElement>(".explorer-row[data-path]") ?? null;
      if (!row) return;
      if (target?.closest(".storage-select")) return;
      const entry = this.entryForRow(row);
      if (!entry) return;
      const menuButton = target?.closest<HTMLButtonElement>(".row-menu-button");
      if (menuButton) {
        event.stopPropagation();
        const rectangle = menuButton.getBoundingClientRect();
        this.prepareContextSelection(entry);
        this.showContextMenu(rectangle.right, rectangle.bottom, entry);
        return;
      }
      const index = Number.parseInt(row.dataset.index ?? "", 10);
      if (Number.isInteger(index)) this.handleRowSelection(entry, index, event);
    });
    this.elements.storageBody.addEventListener("change", (event) => {
      const selector = (event.target as Element | null)?.closest<HTMLInputElement>(".storage-select");
      const row = selector?.closest<HTMLElement>(".explorer-row[data-path]");
      const path = row?.dataset.path;
      if (selector && path) this.setFileSelected(path, selector.checked);
    });
    this.elements.storageBody.addEventListener("dblclick", (event) => {
      const target = event.target as Element | null;
      if (target?.closest(".storage-select, .row-menu-button")) return;
      const row = target?.closest<HTMLElement>(".explorer-row[data-path]") ?? null;
      const entry = this.entryForRow(row);
      if (!entry) return;
      void this.runAction(async () => {
        if (entry.isDirectory) await this.browse(entry.path);
        else await this.download(entry.path);
      });
    });
    this.elements.storageBody.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      const row = (event.target as Element | null)?.closest<HTMLElement>(".explorer-row[data-path]") ?? null;
      const entry = this.entryForRow(row);
      if (entry) this.prepareContextSelection(entry);
      this.showContextMenu(event.clientX, event.clientY, entry);
    });
    this.elements.storageBody.addEventListener("keydown", (event) => {
      const row = (event.target as Element | null)?.closest<HTMLElement>(".explorer-row[data-path]") ?? null;
      if (!row || event.target !== row) return;
      const entry = this.entryForRow(row);
      if (!entry) return;
      if (event.key === "Enter") {
        event.preventDefault();
        void this.runAction(async () => {
          if (entry.isDirectory) await this.browse(entry.path);
          else await this.download(entry.path);
        });
      } else if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
        event.preventDefault();
        this.prepareContextSelection(entry);
        const rectangle = row.getBoundingClientRect();
        this.showContextMenu(rectangle.left + 32, rectangle.top + 24, entry);
      }
    });
'''
    text = replace_once_text(text, old_handlers, new_handlers, "delegate Explorer row events")

    text = replace_once_text(
        text,
        '''      empty.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        this.showContextMenu(event.clientX, event.clientY, null);
      });
''',
        "",
        "remove empty-folder context listener",
    )
    text = replace_once_text(
        text,
        '      row.dataset.kind = entry.isDirectory ? "folder" : "file";\n',
        '      row.dataset.kind = entry.isDirectory ? "folder" : "file";\n      row.dataset.index = String(index);\n',
        "store sorted row index",
    )
    text = replace_once_text(
        text,
        '''      selector.addEventListener("click", (event) => event.stopPropagation());
      selector.addEventListener("change", () => this.setFileSelected(entry.path, selector.checked));
''',
        "",
        "remove per-checkbox listeners",
    )
    text = replace_once_text(
        text,
        '''      menuButton.addEventListener("click", (event) => {
        event.stopPropagation();
        const rectangle = menuButton.getBoundingClientRect();
        this.prepareContextSelection(entry);
        this.showContextMenu(rectangle.right, rectangle.bottom, entry);
      });
''',
        "",
        "remove per-menu listener",
    )
    row_handlers = '''      row.addEventListener("click", (event) => this.handleRowSelection(entry, index, event));
      row.addEventListener("dblclick", () => void this.runAction(async () => {
        if (entry.isDirectory) await this.browse(entry.path);
        else await this.download(entry.path);
      }));
      row.addEventListener("contextmenu", (event) => {
        event.preventDefault();
        this.prepareContextSelection(entry);
        this.showContextMenu(event.clientX, event.clientY, entry);
      });
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          void this.runAction(async () => {
            if (entry.isDirectory) await this.browse(entry.path);
            else await this.download(entry.path);
          });
        } else if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
          event.preventDefault();
          this.prepareContextSelection(entry);
          const rectangle = row.getBoundingClientRect();
          this.showContextMenu(rectangle.left + 32, rectangle.top + 24, entry);
        }
      });
'''
    text = replace_once_text(text, row_handlers, "", "remove per-row listeners")
    marker = '  private handleRowSelection(entry: AndroidStorageEntryDto, index: number, event: MouseEvent): void {\n'
    helper = '''  private entryForRow(row: HTMLElement | null): AndroidStorageEntryDto | null {
    const path = row?.dataset.path;
    if (!path) return null;
    return this.#currentEntries.find((entry) => entry.path === path) ?? null;
  }

'''
    text = replace_once_text(text, marker, helper + marker, "add row entry lookup")
    path.write_text(text, encoding="utf-8")

    tests = WEB / "tests/layout.test.mjs"
    source = tests.read_text(encoding="utf-8")
    marker = 'test("Android File Explorer updates selection without rebuilding every row", () => {\n'
    insert = '''test("Android File Explorer delegates row interaction listeners", () => {
  assert.match(transferSource, /storageBody\.addEventListener\("click"/);
  assert.match(transferSource, /storageBody\.addEventListener\("dblclick"/);
  assert.match(transferSource, /storageBody\.addEventListener\("contextmenu"/);
  assert.match(transferSource, /storageBody\.addEventListener\("keydown"/);
  assert.match(transferSource, /row\.dataset\.index = String\(index\)/);
  assert.doesNotMatch(transferSource, /row\.addEventListener\(/);
  assert.doesNotMatch(transferSource, /selector\.addEventListener\(/);
  assert.doesNotMatch(transferSource, /menuButton\.addEventListener\(/);
});

'''
    tests.write_text(replace_once_text(source, marker, insert + marker, "delegation regression insertion"), encoding="utf-8")


def phase6() -> None:
    transfer = WEB / "src/transfer-controller.ts"
    replace_once(transfer, '  #refreshTransfersBusy = false;\n', '  #refreshTransfersBusy = false;\n  #closed = false;\n', "transfer closed flag")
    replace_once(
        transfer,
        '  private bindEvents(): void {\n',
        '''  public close(): void {
    this.#closed = true;
    this.#browseGeneration += 1;
    if (this.#pollTimer !== null) window.clearTimeout(this.#pollTimer);
    this.#pollTimer = null;
  }

  private bindEvents(): void {
''',
        "transfer close method",
    )
    replace_once(
        transfer,
        '  private scheduleTransferRefresh(delay = this.transferRefreshDelay()): void {\n    if (this.#pollTimer !== null) window.clearTimeout(this.#pollTimer);\n',
        '  private scheduleTransferRefresh(delay = this.transferRefreshDelay()): void {\n    if (this.#closed) return;\n    if (this.#pollTimer !== null) window.clearTimeout(this.#pollTimer);\n',
        "prevent transfer reschedule after close",
    )

    auto = WEB / "src/auto-download-controller.ts"
    replace_once(auto, '  #refreshing = false;\n', '  #refreshing = false;\n  #closed = false;\n', "file sync closed flag")
    replace_once(
        auto,
        '  private bindEvents(): void {\n',
        '''  public close(): void {
    this.#closed = true;
    if (this.#timer !== null) window.clearTimeout(this.#timer);
    this.#timer = null;
  }

  private bindEvents(): void {
''',
        "file sync close method",
    )
    replace_once(
        auto,
        '  private scheduleRefresh(delay = this.refreshDelay()): void {\n    if (this.#timer !== null) window.clearTimeout(this.#timer);\n',
        '  private scheduleRefresh(delay = this.refreshDelay()): void {\n    if (this.#closed) return;\n    if (this.#timer !== null) window.clearTimeout(this.#timer);\n',
        "prevent file sync reschedule after close",
    )

    main = WEB / "src/main.ts"
    replace_once(
        main,
        '    window.addEventListener("beforeunload", () => { controller.stopOnUnload(); runningAppController.close(); });\n',
        '    window.addEventListener("beforeunload", () => { controller.stopOnUnload(); runningAppController.close(); transferController.close(); autoDownloadController.close(); });\n',
        "close polling controllers on unload",
    )

    html = WEB / "static/index.html"
    text = html.read_text(encoding="utf-8")
    replacements = (
        ('<!-- DroidWebDisplay Main Single Drawer UI v1.0.0 -->', '<!-- DroidWebDisplay Main Single Drawer UI v1.2.0 -->', "UI version comment"),
        ('droidwebdisplay-main-drawer.css?v=0.11.2-native4', 'droidwebdisplay-main-drawer.css?v=0.11.2-native5', "drawer CSS cache key"),
        ('id="gb-single-drawer-root" data-version="1.1.0"', 'id="gb-single-drawer-root" data-version="1.2.0"', "drawer data version"),
        ('/assets/main.js?v=0.11.2-native1', '/assets/main.js?v=0.11.2-native2', "main asset cache key"),
        ('droidwebdisplay-main-drawer.js?v=0.11.2-native4', 'droidwebdisplay-main-drawer.js?v=0.11.2-native5', "drawer JS cache key"),
    )
    for old, new, label in replacements:
        text = replace_once_text(text, old, new, label)
    html.write_text(text, encoding="utf-8")

    drawer_js = WEB / "static/droidwebdisplay-main-drawer.js"
    replace_once(drawer_js, '/* DroidWebDisplay native single-drawer controller v1.7.0 */', '/* DroidWebDisplay native single-drawer controller v1.8.0 */', "drawer controller version")

    drawer_css = WEB / "static/droidwebdisplay-main-drawer.css"
    css = drawer_css.read_text(encoding="utf-8")
    css = replace_once_text(css, '/* DroidWebDisplay Web GUI Theme v1.0', '/* DroidWebDisplay Web GUI Theme v1.1', "drawer stylesheet version")
    css, count = re.subn(r'^\.gb-rail-button\[data-group="apps"\] \.gb-rail-icon \{.*\}\n', '', css, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"remove obsolete Apps rail icon: expected one match, found {count}")
    drawer_css.write_text(css, encoding="utf-8")

    tests = WEB / "tests/layout.test.mjs"
    source = tests.read_text(encoding="utf-8")
    marker = 'test("idle file polling is adaptive and visibility aware", () => {\n'
    insert = '''test("polling controllers stop cleanly and static asset versions advance", () => {
  assert.match(transferSource, /public close\(\): void/);
  assert.match(transferSource, /if \(this\.#closed\) return/);
  assert.match(autoDownloadSource, /public close\(\): void/);
  assert.match(mainSource, /transferController\.close\(\); autoDownloadController\.close\(\)/);
  assert.match(html, /main\.js\?v=0\.11\.2-native2/);
  assert.match(html, /droidwebdisplay-main-drawer\.css\?v=0\.11\.2-native5/);
  assert.match(html, /droidwebdisplay-main-drawer\.js\?v=0\.11\.2-native5/);
  assert.doesNotMatch(drawerCssSource, /data-group="apps"/);
});

'''
    source = replace_once_text(source, 'const drawerSource = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.js"), "utf8");\n', 'const drawerSource = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.js"), "utf8");\nconst drawerCssSource = await readFile(resolve(root, "static/droidwebdisplay-main-drawer.css"), "utf8");\n', "load drawer CSS source")
    tests.write_text(replace_once_text(source, marker, insert + marker, "lifecycle regression insertion"), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("5", "6"))
    args = parser.parse_args()
    {"5": phase5, "6": phase6}[args.phase]()


if __name__ == "__main__":
    main()
