"""DroidWebDisplay runtime package."""

__version__ = "0.11.2"
RELEASE_PHASE = 11

# Install compatibility-preserving hardened runtime classes before consumers
# import concrete submodules such as droid_web_display.scrcpy.session.
from .runtime_hardening import install_runtime_hardening

install_runtime_hardening()

del install_runtime_hardening
