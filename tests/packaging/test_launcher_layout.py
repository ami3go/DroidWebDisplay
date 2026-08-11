from pathlib import Path


def test_packaged_launchers_support_installed_venv_and_platform_layout() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "gpt_bridge/release_packaging.py").read_text(encoding="utf-8")
    assert 'Join-Path $Root ".venv\\\\Scripts\\\\python.exe"' in source or 'Join-Path $Root ".venv\\Scripts\\python.exe"' in source
    assert 'PYTHON="$ROOT/.venv/bin/python3"' in source
    assert 'output / "packaging" / inputs.target' in source
    assert 'output / "installer"' not in source


def test_runtime_package_contains_stop_tool_and_pyproject() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "gpt_bridge/release_packaging.py").read_text(encoding="utf-8")
    assert '"tools/stop_bridge_service.py"' in source
    assert '"pyproject.toml"' in source
