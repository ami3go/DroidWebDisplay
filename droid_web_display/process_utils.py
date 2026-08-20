"""Shared subprocess launch policy.

Every child process this app spawns is a background helper the user never
interacts with. On Windows each one would otherwise pop a console window, so
the CREATE_NO_WINDOW flag has to be applied consistently. It previously lived
inline in three modules with two different fallbacks, and the firewall call
had none at all, so it is centralised here.
"""

from __future__ import annotations

import os
import subprocess

# subprocess.CREATE_NO_WINDOW exists on Windows CPython 3.7+. The literal
# keeps the contract testable from non-Windows runtimes, where the attribute
# is absent.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def subprocess_creation_kwargs(platform_name: str | None = None) -> dict[str, int]:
    """Return platform-specific flags for invisible background child processes."""
    if (platform_name or os.name) != "nt":
        return {}
    return {"creationflags": CREATE_NO_WINDOW}
