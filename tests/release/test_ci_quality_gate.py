from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_release_ci_requires_lint_and_behavioral_regressions() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "ruff check droid_web_display tools tests" in workflow
    assert "tests/security" in workflow
    assert "tests/regression/transfers" in workflow
    assert "tests/regression/test_clipboard_copy_server_mode.py" in workflow
    assert "tools/release_gate.py --require-web-client-build" in workflow
