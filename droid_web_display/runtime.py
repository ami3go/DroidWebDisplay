"""Runtime dependency checks for the local bridge service."""

from __future__ import annotations

from importlib.util import find_spec


WEBSOCKET_BACKENDS = ("websockets", "wsproto")


def find_websocket_backend() -> str | None:
    """Return the first WebSocket backend available to Uvicorn."""

    for module_name in WEBSOCKET_BACKENDS:
        if find_spec(module_name) is not None:
            return module_name
    return None


def require_websocket_backend() -> str:
    """Require a WebSocket implementation and return its module name.

    Uvicorn can serve ordinary HTTP without an optional WebSocket backend, which
    otherwise produces a misleading healthy startup followed by 404 responses
    for every browser WebSocket upgrade.
    """

    backend = find_websocket_backend()
    if backend is None:
        raise RuntimeError(
            "No Python WebSocket backend is installed. Run `uv sync --locked` "
            "from the DroidWebDisplay repository root, then restart the service."
        )
    return backend
