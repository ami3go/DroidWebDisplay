from __future__ import annotations

from typing import Any

from .app import create_app as _create_app
from .release_metadata import install_release_metadata


def create_app(*args: Any, **kwargs: Any):
    """Create the public DroidWebDisplay API with canonical release metadata."""

    return install_release_metadata(_create_app(*args, **kwargs))


__all__ = ["create_app"]
