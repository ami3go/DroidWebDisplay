from __future__ import annotations

from typing import Any

from .app import create_app as _create_app
from .latency import install_latency_api
from .release_metadata import install_release_metadata


def create_app(*args: Any, **kwargs: Any):
    """Create the public DroidWebDisplay API with release and latency extensions."""

    app = _create_app(*args, **kwargs)
    install_latency_api(app)
    return install_release_metadata(app)


__all__ = ["create_app"]
