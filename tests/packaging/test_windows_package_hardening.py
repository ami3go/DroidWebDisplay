from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_windows_pyinstaller_targets_disable_upx_and_embed_metadata() -> None:
    portable = (ROOT / "packaging/pyinstaller/DroidWebDisplayWindows.spec").read_text(encoding="utf-8")
    onedir = (ROOT / "packaging/pyinstaller/DroidWebDisplayWindowsOnedir.spec").read_text(encoding="utf-8")
    for text in (portable, onedir):
        assert "upx=False" in text
        assert "ProductName" in text
        assert "ProductVersion" in text
        assert "OriginalFilename" in text
        assert 'with_suffix(".ico.base64")' in text
    assert "runtime_tmpdir=None" in portable
    assert 'name="DroidWebDisplayWindowsOnedir"' in onedir


def test_windows_icon_source_is_present() -> None:
    icon = ROOT / "packaging/windows/droidwebdisplay.ico.base64"
    assert icon.is_file()
    assert len(icon.read_text(encoding="ascii").strip()) > 1024


def test_windows_ci_builds_and_smokes_both_distribution_forms() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "DroidWebDisplayWindows.spec" in workflow
    assert "DroidWebDisplayWindowsOnedir.spec" in workflow
    assert "DroidWebDisplay-windows-x86_64.zip" in workflow
    assert "--adb-smoke" in workflow
    assert "Repeat Windows service start-stop smoke" in workflow
    assert "Verify Windows PE metadata and bundled ADB" in workflow
    assert "Build web client before integrity checks" in workflow


def test_future_releases_publish_stable_windows_zip() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert 'DroidWebDisplay-v${RELEASE_VERSION}-windows-x86_64.exe' in workflow
    assert 'DroidWebDisplay-v${RELEASE_VERSION}-windows-x86_64.zip' in workflow


def test_desktop_package_has_bundled_adb_self_test() -> None:
    entry = (ROOT / "tools/desktop_entry.py").read_text(encoding="utf-8")
    assert '"--adb-smoke"' in entry
    assert 'subprocess.run([str(adb), "version"]' in entry
    assert "CREATE_NO_WINDOW" in entry


def test_web_client_surfaces_windows_adb_and_black_video_guidance() -> None:
    main = (ROOT / "apps/web-client/src/main.ts").read_text(encoding="utf-8")
    browser = (ROOT / "apps/web-client/src/browser-support.ts").read_text(encoding="utf-8")
    assert "USB authorization required" in main
    assert "OEM USB driver" in main
    assert "ADB device offline" in main
    assert "browserGpuRenderer" in main
    assert "disable browser hardware acceleration" in main
    assert "browserName" in browser
    assert "hardwareConcurrency" in browser
