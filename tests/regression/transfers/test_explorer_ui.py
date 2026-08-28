from pathlib import Path


def test_explorer_file_browser_and_context_menu_are_bundled() -> None:
    root = Path(__file__).resolve().parents[3]
    html = (root / "apps/web-client/dist/index.html").read_text(encoding="utf-8")
    script = (root / "apps/web-client/dist/assets/transfer-controller.js").read_text(encoding="utf-8")
    style = "\n".join(
        (root / path).read_text(encoding="utf-8")
        for path in (
            "apps/web-client/dist/styles.css",
            "apps/web-client/dist/droidwebdisplay-main-drawer-core.css",
        )
    )

    for element_id in (
        'id="storage-breadcrumbs"',
        'id="storage-select-all"',
        'id="storage-context-menu"',
        'id="context-open"',
        'id="context-download"',
        'id="context-upload"',
        'id="context-delete"',
        'id="context-refresh"',
        'id="context-upload-file"',
        'id="file-browser-tab"',
        'id="recent-pictures-tab"',
        'id="recent-pictures-refresh"',
        'id="recent-pictures-controls"',
    ):
        assert element_id in html

    assert "contextmenu" in script
    assert "Upload to current folder" in script
    assert "sortStorageEntries" in script
    assert "androidRecentPictures" in script
    assert "Queued ${selected.length} download(s)" in script
    assert 'id="download-selected" class="secondary" disabled>Download<' in html
    assert ".explorer-row" in style
    assert ".explorer-tab" in style
    assert ".context-menu" in style
