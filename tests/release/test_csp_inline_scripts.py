from __future__ import annotations

import base64
import hashlib
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]


def _inline_scripts(html: str) -> list[str]:
    return re.findall(
        r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )


def _sha256_source(script: str) -> str:
    digest = hashlib.sha256(script.encode("utf-8")).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def test_server_csp_allows_every_inline_web_script() -> None:
    html = (ROOT / "apps" / "web-client" / "dist" / "index.html").read_text(encoding="utf-8")
    app_source = (ROOT / "droid_web_display" / "api" / "app.py").read_text(encoding="utf-8")

    scripts = _inline_scripts(html)
    assert scripts, "Expected at least one inline script/import map in dist/index.html"

    for script in scripts:
        source = _sha256_source(script)
        assert source in app_source, f"CSP is missing hash for current inline script: {source}"


def test_droidwebdisplay_import_map_hash_is_current() -> None:
    html = (ROOT / "apps" / "web-client" / "dist" / "index.html").read_text(encoding="utf-8")
    match = re.search(
        r"<script[^>]*type=[\"']importmap[\"'][^>]*>(.*?)</script>",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )

    assert match is not None
    assert "@droid-web-display/scrcpy-protocol" in match.group(1)
    assert _sha256_source(match.group(1)) == "sha256-0u7HdijpKCtbMJSF/CxBDiwEw6/NSTMjgCYEMe9Byl0="
