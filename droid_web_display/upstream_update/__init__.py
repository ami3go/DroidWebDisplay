"""Controlled scrcpy upstream update automation."""

from .compatibility import PromotionError, promote_adapter, register_experimental_adapter
from .inspection import inspect_protocol_changes, write_protocol_report
from .patches import PatchApplicationError, apply_patch_series
from .scaffold import AdapterScaffoldError, scaffold_adapter

__all__ = [
    "AdapterScaffoldError",
    "PatchApplicationError",
    "PromotionError",
    "apply_patch_series",
    "inspect_protocol_changes",
    "promote_adapter",
    "register_experimental_adapter",
    "scaffold_adapter",
    "write_protocol_report",
]
