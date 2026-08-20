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
        # The icon must come from the tracked base64 source. The specs delegate
        # that to _dwd_common.windows_icon, which is asserted below; pinning the
        # exact path expression here broke on a refactor that changed nothing
        # about the behaviour.
        assert "icon=str(ICON)" in text
    assert "runtime_tmpdir=None" in portable
    assert 'name="DroidWebDisplayWindowsOnedir"' in onedir


def test_windows_icon_is_decoded_from_the_tracked_source_into_the_build_dir(tmp_path) -> None:
    """The icon is generated, so it must not be written back into the checkout.

    packaging/windows/droidwebdisplay.ico is not gitignored; writing it there
    left an untracked binary after every build.
    """
    common = (ROOT / "packaging/pyinstaller/_dwd_common.py").read_text(encoding="utf-8")
    assert "droidwebdisplay.ico.base64" in common
    for name in ("DroidWebDisplayWindows.spec", "DroidWebDisplayWindowsOnedir.spec"):
        spec = (ROOT / "packaging/pyinstaller" / name).read_text(encoding="utf-8")
        assert "common.windows_icon(" in spec, name
        assert 'ROOT / "packaging" / "windows" / "droidwebdisplay.ico"' not in spec, name


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
