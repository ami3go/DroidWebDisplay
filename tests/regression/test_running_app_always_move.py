from pathlib import Path


def test_running_app_endpoint_always_attempts_relocation() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "droid_web_display" / "api" / "app.py").read_text(encoding="utf-8")
    start = source.index('@app.post("/api/v1/sessions/{session_id}/virtual-display/move-running-app")')
    end = source.find("\n    @app.", start + 1)
    route = source[start:] if end < 0 else source[start:end]
    assert "if selected.display_id == session.display_id" not in route
    assert "move_running_app_to_display(" in route
