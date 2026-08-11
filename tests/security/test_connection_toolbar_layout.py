from pathlib import Path


def test_connection_toolbar_is_left_aligned_and_inline() -> None:
    root = Path(__file__).resolve().parents[2]
    css = (root / "apps/web-client/static/styles.css").read_text(encoding="utf-8")
    html = (root / "apps/web-client/static/index.html").read_text(encoding="utf-8")
    assert 'class="connection-row"' in html
    assert 'justify-content: flex-start' in css
    assert '.connection-row button { white-space: nowrap; flex: 0 0 auto; }' in css
    assert '.connection-row select { flex: 1 1 20rem; max-width: 28rem; }' in css


def test_connection_status_is_compact_toolbar_control() -> None:
    root = Path(__file__).resolve().parents[2]
    css = (root / "apps/web-client/static/styles.css").read_text(encoding="utf-8")
    html = (root / "apps/web-client/static/index.html").read_text(encoding="utf-8")
    header = html[html.index('<header class="topbar">'):html.index('</header>', html.index('<header class="topbar">'))]
    assert 'id="connection-status"' in header
    assert 'id="status-icon"' in header
    assert 'class="status-card"' not in html
    assert '.connection-status {' in css
    assert 'height: 2.12rem' in css
    assert '.connection-status[data-state="connected"]' in css
    assert '.connection-status[data-state="disconnected"]' in css
