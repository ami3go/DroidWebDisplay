from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_ORDER = "['display','clipboard','files','apps','audio','access','network','diagnostics','settings']"


def test_drawer_icon_order_is_product_order() -> None:
    for relative in (
        Path("apps/web-client/static/droidwebdisplay-main-drawer.js"),
        Path("apps/web-client/dist/droidwebdisplay-main-drawer.js"),
    ):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert f"const GROUPS = {EXPECTED_ORDER};" in source
        assert "function applyRailOrder()" in source
        assert "applyRailOrder();" in source


def test_static_and_dist_drawer_controller_match() -> None:
    static = (ROOT / "apps/web-client/static/droidwebdisplay-main-drawer.js").read_text(encoding="utf-8")
    dist = (ROOT / "apps/web-client/dist/droidwebdisplay-main-drawer.js").read_text(encoding="utf-8")
    assert static == dist
