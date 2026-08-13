from pathlib import Path


def test_web_client_has_no_legacy_gpt_bridge_branding() -> None:
    root = Path(__file__).resolve().parents[2]
    web = root / "apps" / "web-client"
    legacy = ("GptBridge", "GPT Bridge", "Gpt-Bridge", "gpt_bridge", "gpt-bridge", "gptBridge")
    offenders = []
    for path in [web / "static" / "index.html", web / "static" / "droidwebdisplay-main-drawer.js", web / "src" / "main.ts", web / "src" / "controller.ts"]:
        text = path.read_text(encoding="utf-8")
        for token in legacy:
            if token in text:
                offenders.append(f"{path.relative_to(root)}: {token}")
    assert offenders == []


def test_native_single_drawer_is_source_of_truth() -> None:
    root = Path(__file__).resolve().parents[2]
    html = (root / "apps" / "web-client" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'data-ui="droidwebdisplay-native-single-drawer-v1"' in html
    assert 'id="gb-single-drawer-root"' in html
    assert '<aside class="sidepanel">' not in html
    assert '<aside class="transfer-panel"' not in html
    assert 'id="workspace-layout"' not in html
    for label in ("Display", "Clipboard", "Files", "Audio", "Access", "Network", "Diagnostics", "Settings"):
        assert f'>{label}<' in html
