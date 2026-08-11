from pathlib import Path


def test_repository_contains_no_legacy_phase_artifacts() -> None:
    root = Path(__file__).resolve().parents[2]
    forbidden = []
    forbidden.extend(root.glob(".github/workflows/phase[1-7]-*.yml"))
    forbidden.extend(root.glob("docs/PHASE[1-7]*"))
    forbidden.extend(root.glob("scripts/phase[1-7]-*"))
    forbidden.extend(root.glob("tools/phase[1-7]_*.py"))
    forbidden.extend(root.glob("tests/phase[1-7]"))
    assert not forbidden, [str(path.relative_to(root)) for path in forbidden]
