from pathlib import Path
import subprocess

CONFLICT_MARKERS = ("<<<<<<< ", ">>>>>>> ")
GENERATED_PREFIXES = (
    "apps/web-client/dist/",
    "packages/scrcpy-protocol/dist/",
    "node_modules/",
    "server/",
)
BINARY_SUFFIXES = {
    ".7z", ".aab", ".apk", ".dll", ".dylib", ".exe", ".gif", ".gz", ".ico",
    ".jar", ".jpeg", ".jpg", ".pdf", ".png", ".so", ".ttf", ".webp", ".woff",
    ".woff2", ".xz", ".zip",
}


def _tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [root / raw.decode("utf-8") for raw in result.stdout.split(b"\0") if raw]


def _skip_conflict_scan(relative: Path) -> bool:
    normalized = relative.as_posix()
    return normalized.startswith(GENERATED_PREFIXES) or relative.suffix.lower() in BINARY_SUFFIXES


def test_repository_contains_no_legacy_phase_artifacts() -> None:
    root = Path(__file__).resolve().parents[2]
    forbidden = []
    forbidden.extend(root.glob(".github/workflows/phase[1-7]-*.yml"))
    forbidden.extend(root.glob("docs/PHASE[1-7]*"))
    forbidden.extend(root.glob("scripts/phase[1-7]-*"))
    forbidden.extend(root.glob("tools/phase[1-7]_*.py"))
    forbidden.extend(root.glob("tests/phase[1-7]"))
    assert not forbidden, [str(path.relative_to(root)) for path in forbidden]


def test_repository_contains_no_merge_conflict_markers() -> None:
    root = Path(__file__).resolve().parents[2]
    conflicts: list[str] = []

    for path in _tracked_files(root):
        relative = path.relative_to(root)
        if _skip_conflict_scan(relative) or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if line.startswith(CONFLICT_MARKERS) or line == "=======":
                conflicts.append(f"{relative.as_posix()}:{line_number}: {line}")

    assert not conflicts, "Unresolved merge conflict markers found:\n" + "\n".join(conflicts)
