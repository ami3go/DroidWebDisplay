from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_ORDER = ("display", "clipboard", "files", "audio", "access", "diagnostics", "settings")


def test_drawer_icon_order_is_product_order() -> None:
    for relative in (
        Path("apps/web-client/static/index.html"),
        Path("apps/web-client/dist/index.html"),
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        positions = [source.index(f'data-group="{group}"') for group in EXPECTED_ORDER]
        assert positions == sorted(positions)
        assert 'data-group="network"' not in source
        assert 'data-group="apps"' not in source

    for relative in (
        Path("apps/web-client/static/droidwebdisplay-main-drawer.js"),
        Path("apps/web-client/dist/droidwebdisplay-main-drawer.js"),
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert f"const GROUPS = {list(EXPECTED_ORDER)!r};".replace(" ", "") in source.replace(" ", "")
        assert "function applyRailOrder()" not in source
        assert "applyRailOrder();" not in source


def test_static_and_dist_drawer_controller_match() -> None:
    static = (ROOT / "apps/web-client/static/droidwebdisplay-main-drawer.js").read_text(encoding="utf-8")
    dist = (ROOT / "apps/web-client/dist/droidwebdisplay-main-drawer.js").read_text(encoding="utf-8")
    assert static == dist
