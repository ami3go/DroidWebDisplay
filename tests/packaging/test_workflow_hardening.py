from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_release_candidate_is_qualified_before_main_is_promoted() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    prepare, publish = workflow.split("\n  publish:\n", 1)
    assert "release-candidate/v${version}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" in prepare
    assert 'git push origin HEAD:"refs/heads/$release_ref"' in prepare
    assert "git push origin HEAD:main" not in prepare
    assert publish.index('gh run watch "$run_id"') < publish.index('git push origin "$RELEASE_SHA:refs/heads/main"')


def test_release_workflow_allows_same_version_recovery() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert 'if current == version:' in workflow
    assert "VERSION already equals" not in workflow
    assert 'release_ref="main"' in workflow
    assert 'promote="false"' in workflow


def test_ci_detects_generated_artifact_drift_after_build() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "Verify committed generated artifacts match source" in workflow
    assert "git status --porcelain --" in workflow
    assert "packages/scrcpy-protocol/dist" in workflow
    assert "apps/web-client/dist-manifest.json" in workflow


def test_appimage_verification_has_no_find_head_pipe() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    appimage = workflow.split("- name: Verify AppImage version metadata and bundled ADB", 1)[1]
    assert "| head -n 1" not in appimage
    assert 'mapfile -t bundled_versions' in appimage
    assert 'mapfile -t adbs' in appimage
