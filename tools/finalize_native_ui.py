#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"Missing finalization anchor: {label}")
    return text.replace(old, new, 1)


def fix_context_menu() -> None:
    path = ROOT / "apps/web-client/static/index.html"
    text = path.read_text(encoding="utf-8")
    old = '''          <div class="context-separator" role="separator"></div>
<details class="gb-accordion" data-section-key="files-sync">'''
    new = '''          <div class="context-separator" role="separator"></div>
          <button id="context-refresh" type="button" role="menuitem">Refresh</button>
        </div>
<details class="gb-accordion" data-section-key="files-sync">'''
    path.write_text(replace_once(text, old, new, "context menu"), encoding="utf-8")


def update_phase9_tests() -> None:
    path = ROOT / "tests/ux/test_phase9.py"
    text = path.read_text(encoding="utf-8")
    start = text.index("def test_requested_button_labels_and_legacy_gate_controls_are_removed() -> None:")
    end = text.index("\ndef test_audio_server_mapping_uses_opus_and_keeps_channel_order()", start)
    replacement = '''def test_requested_button_labels_and_legacy_gate_controls_are_removed() -> None:
    html = (ROOT / "apps/web-client/dist/index.html").read_text(encoding="utf-8")
    assert '>Load<' in html
    assert '>Browse<' in html
    assert '>Download<' in html
    assert '>Reset<' in html
    for old in ("Upload selected file(s)", "Browse upload folder", "Download selected", "Reset history", ">Upload<"):
        assert old not in html
    assert "data-gate4-check" not in html
    assert "data-gate5-check" not in html
    assert "data-gate6-check" not in html
    assert "data-gate7-check" not in html
    assert "verification" not in html


def test_phase9_native_layout_audio_clipboard_and_reconnect_controls_are_bundled() -> None:
    html = (ROOT / "apps/web-client/dist/index.html").read_text(encoding="utf-8")
    css = (ROOT / "apps/web-client/dist/styles.css").read_text(encoding="utf-8")
    for element_id in (
        'id="audio-enabled"', 'id="audio-mute"', 'id="audio-volume"',
        'id="auto-reconnect"', 'id="reconnect"',
        'id="clipboard-auto-sync"', 'id="clipboard-max-kib"',
        'id="clipboard-copy-android"', 'id="settings-export"', 'id="settings-import"',
        'id="gb-single-drawer-root"',
    ):
        assert element_id in html
    assert 'data-ui="droidwebdisplay-native-single-drawer-v1"' in html
    assert 'id="workspace-layout"' not in html
    assert '<aside class="sidepanel">' not in html
    assert '<aside class="transfer-panel"' not in html
    assert "#screen { cursor: default; }" in css
    assert ".uniform-buttons > button" in css
    assert "<h2>Audio</h2>" in html
    assert "Audio experimental" not in html
    assert "Experimental:" not in html
    assert "Browser audio may have interruptions or delay" in html
    assert 'id="auto-upload-enabled"' in html
    assert 'id="auto-upload-duplicate"' in html
    assert 'id="auto-upload-existing"' in html
    assert 'id="exit-focus"' not in html
    assert "<h2>Controls</h2>" not in html
    assert 'class="status-ring-progress"' in html
    assert "connection-ring-spin" in css
    assert ">Paste</button>" in html
    assert ">Type</button>" in html
    assert ">Copy</button>" in html
    for group in ("apps", "files", "clipboard", "display", "audio", "access", "network", "diagnostics", "settings"):
        assert f'data-group="{group}"' in html

'''
    path.write_text(text[:start] + replacement + text[end + 1 :], encoding="utf-8")


def update_release_gate() -> None:
    path = ROOT / "tools/release_gate.py"
    text = path.read_text(encoding="utf-8")

    old = '''    checks["reconnectAndLayout"] = {
        "status": "PASS" if all(token in controller_source + html_source + css_source for token in (
            "scheduleReconnect", "reconnectNow", "requestFullscreen", 'id="workspace-layout"', ':focus-visible', 'aria-live="polite"',
        )) else "FAIL",
        "automaticReconnect": True,
        "manualReconnect": True,
        "fullscreen": True,
        "keyboardFocus": True,
    }
'''
    new = '''    permanent_native_layout = (
        'data-ui="droidwebdisplay-native-single-drawer-v1"' in html_source
        and 'id="gb-single-drawer-root"' in html_source
        and 'id="workspace-layout"' not in html_source
        and '<aside class="sidepanel">' not in html_source
        and '<aside class="transfer-panel"' not in html_source
        and "workspaceLayout" not in controller_source
    )
    checks["reconnectAndLayout"] = {
        "status": "PASS" if permanent_native_layout and all(token in controller_source + html_source + css_source for token in (
            "scheduleReconnect", "reconnectNow", "requestFullscreen", ':focus-visible', 'aria-live="polite"',
        )) else "FAIL",
        "automaticReconnect": True,
        "manualReconnect": True,
        "fullscreen": True,
        "keyboardFocus": True,
        "permanentNativeLayout": permanent_native_layout,
    }
'''
    text = replace_once(text, old, new, "reconnectAndLayout")

    old = '''    compact_labels = all(token in html_source for token in (">Upload<", ">Browse<", ">Download<", ">Reset<", ">Save<", ">Scan now<"))
'''
    new = '''    compact_labels = all(token in html_source for token in (">Load<", ">Browse<", ">Download<", ">Reset<", ">Save<", ">Scan now<")) and ">Upload<" not in html_source
'''
    text = replace_once(text, old, new, "compact labels")

    old = '''    collapse_tokens = ("initializeCollapsibleCards", "card-collapse-button", "collapsible-card", "is-collapsed", 'aria-expanded", "true"')
    checks["collapsibleCards"] = {
        "status": "PASS" if all(token in html_source + css_source + main_source for token in collapse_tokens) else "FAIL",
        "expandedByDefault": 'aria-expanded", "true"' in main_source,
        "leftAndRightPanels": ".sidepanel > .help-card, .transfer-panel > .help-card" in main_source,
        "obsoleteControlsCardRemoved": "<h2>Controls</h2>" not in html_source,
    }
    checks["singlePageVerticalScroll"] = {
        "status": "PASS" if all(token in css_source for token in (
            ".workspace { flex: 1; min-height: 0; display: grid; grid-template-columns: 280px 1fr; align-items: start;",
            ".transfer-panel { display: flex; min-width: 0; flex-direction: column; gap: 1rem; overflow: visible; max-height: none;",
        )) and "overflow: auto; max-height: calc(100vh - 72px);" not in css_source else "FAIL",
        "pageScrollbarOnly": True,
        "rightPanelOwnScrollbar": False,
        "workspaceTopAligned": True,
    }

    checks["focusLayoutEscape"] = {
        "status": "PASS" if all(token in html_source + controller_source for token in (
            'id="fullscreen"', 'id="workspace-layout"', 'workspaceLayout.addEventListener("change", () => this.applyWorkspaceLayout())',
        )) and 'id="exit-focus"' not in html_source and "exitFocus" not in controller_source else "FAIL",
        "toolbarPlacement": True,
        "selectorAlwaysVisible": True,
        "dedicatedExitButton": False,
    }
'''
    new = '''    drawer_source = (root / "apps/web-client/static/droidwebdisplay-main-drawer.js").read_text(encoding="utf-8")
    native_accordion_contract = all(token in html_source for token in (
        'id="gb-single-drawer-root"', 'data-section-key="files-load"', 'data-section-key="files-sync"',
        'data-section-key="access-web-browser"', 'data-section-key="access-pin"', 'data-section-key="access-revoke-all"',
    )) and "droidwebdisplay.ui.drawer.accordions.v1" in drawer_source
    checks["collapsibleCards"] = {
        "status": "PASS" if native_accordion_contract and permanent_native_layout and "initializeCollapsibleCards" not in main_source else "FAIL",
        "nativePersistedAccordions": native_accordion_contract,
        "legacyPanelsPresent": '<aside class="sidepanel">' in html_source or '<aside class="transfer-panel"' in html_source,
        "obsoleteControlsCardRemoved": "<h2>Controls</h2>" not in html_source,
    }
    checks["singlePageVerticalScroll"] = {
        "status": "PASS" if permanent_native_layout and ".native-workspace" in css_source and "overflow: auto; max-height: calc(100vh - 72px);" not in css_source else "FAIL",
        "pageScrollbarOnly": True,
        "rightPanelOwnScrollbar": False,
        "workspaceTopAligned": True,
        "nativeWorkspace": True,
    }

    checks["focusLayoutEscape"] = {
        "status": "PASS" if permanent_native_layout and 'id="fullscreen"' in html_source and 'id="exit-focus"' not in html_source and "exitFocus" not in controller_source else "FAIL",
        "toolbarPlacement": True,
        "selectorAlwaysVisible": False,
        "selectorPresent": 'id="workspace-layout"' in html_source,
        "permanentFocusStyle": True,
        "dedicatedExitButton": False,
    }
'''
    text = replace_once(text, old, new, "native layout gate")
    path.write_text(text, encoding="utf-8")


def verify_source() -> None:
    html = (ROOT / "apps/web-client/static/index.html").read_text(encoding="utf-8")
    for token in (
        '<title>DroidWebDisplay</title>',
        'data-ui="droidwebdisplay-native-single-drawer-v1"',
        'id="gb-single-drawer-root"',
        'id="context-refresh"',
        'id="clipboard-auto-sync"',
    ):
        if token not in html:
            raise RuntimeError(f"Required native UI token missing: {token}")
    for token in ('id="workspace-layout"', '<aside class="sidepanel">', '<aside class="transfer-panel"'):
        if token in html:
            raise RuntimeError(f"Legacy UI token remains: {token}")


def main() -> int:
    fix_context_menu()
    update_phase9_tests()
    update_release_gate()
    verify_source()
    print("Final native DroidWebDisplay UI patch applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
