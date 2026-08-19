from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_ci_runs_on_immutable_release_ref() -> None:
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")

    assert 'release_ref="release/v${version}"' in workflow
    assert "git push --atomic origin HEAD:main HEAD:refs/heads/${release_ref}" in workflow
    assert 'gh workflow run ci.yml --repo "$GITHUB_REPOSITORY" --ref "$RELEASE_REF"' in workflow
    assert 'ref_sha=$(gh api "repos/$GITHUB_REPOSITORY/commits/$RELEASE_REF" --jq .sha)' in workflow
    assert "commits/main" not in workflow
    assert 'if [ "$current" != "$RELEASE_SHA" ]' not in workflow
    assert '--target "$RELEASE_SHA"' in workflow
