from __future__ import annotations

from typing import Any

from starlette.routing import Mount

from .app import create_app as _create_app
from .latency import install_latency_api
from .profiles import install_profiles_api
from .release_metadata import install_release_metadata


def _promote_extension_routes(app, start_index: int) -> None:
    """Keep APIs installed after the base app ahead of the catch-all web mount."""

    extension_routes = list(app.router.routes[start_index:])
    if not extension_routes:
        return
    del app.router.routes[start_index:]
    mount_index = next(
        (
            index
            for index, route in enumerate(app.router.routes)
            if isinstance(route, Mount) and getattr(route, "path", "") in {"", "/"}
        ),
        len(app.router.routes),
    )
    app.router.routes[mount_index:mount_index] = extension_routes


def create_app(*args: Any, **kwargs: Any):
    """Create the public DroidWebDisplay API with release, latency and profile extensions."""

    app = _create_app(*args, **kwargs)
    extension_start = len(app.router.routes)
    install_latency_api(app)
    install_profiles_api(app)
    _promote_extension_routes(app, extension_start)
    return install_release_metadata(app)


__all__ = ["create_app"]
