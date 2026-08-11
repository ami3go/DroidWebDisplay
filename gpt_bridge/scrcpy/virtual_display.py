from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from gpt_bridge.models import AndroidDevice, DisplayImePolicy, VirtualDisplayOptions

_NEW_DISPLAY_RE = re.compile(
    r"New display:\s*(?P<width>\d+)x(?P<height>\d+)/(?P<dpi>\d+)\s*\(id=(?P<id>\d+)\)"
)
_APP_START_RE = re.compile(r"(?:Starting app|Start app|Activity started).*?(?P<package>[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+)", re.I)
_APP_ERROR_RE = re.compile(r"(?:Could not|Unable to|Failed to).*?(?:start|find).*?app", re.I)

_IME_POLICY_FAILURE_MARKERS = (
    "setdisplayimepolicy",
    "attempted to set ime policy to an untrusted virtual display",
    "display ime policy",
)


def samsung_local_ime_policy_risk(device: AndroidDevice) -> bool:
    """Detect Samsung Android 12/13 builds that may reject local VD IME policy."""
    manufacturer = (device.manufacturer or "").strip().lower()
    sdk = device.sdk or 0
    return manufacturer == "samsung" and 31 <= sdk <= 33


def apply_device_virtual_display_compatibility(
    device: AndroidDevice,
    options: VirtualDisplayOptions,
) -> tuple[VirtualDisplayOptions, list[str], bool]:
    """Apply deterministic device-specific fallbacks before launching scrcpy."""
    warnings: list[str] = []
    fallback = False
    effective = options
    if options.ime_policy == DisplayImePolicy.LOCAL and samsung_local_ime_policy_risk(device):
        effective = replace(options, ime_policy=DisplayImePolicy.DEFAULT)
        fallback = True
        warnings.append(
            "Samsung Android 12/13 may reject local IME policy on an untrusted virtual display; "
            "using Android default IME routing."
        )
    return effective, warnings, fallback


def classify_virtual_display_failure(lines: list[str] | tuple[str, ...]) -> str:
    text = "\n".join(lines).lower()
    if "stack corruption detected" in text or "-fstack-protector" in text:
        return "app-process-stack-corruption"
    if any(marker in text for marker in _IME_POLICY_FAILURE_MARKERS):
        return "ime-policy-rejected"
    if "could not create display" in text or "createnewvirtualdisplay" in text:
        return "display-security-rejected" if "securityexception" in text else "display-creation-failed"
    if "encoder" in text and any(token in text for token in ("failed", "error", "could not")):
        return "encoder-initialization-failed"
    if "server version" in text and "does not match" in text:
        return "server-version-mismatch"
    if "new display:" not in text:
        return "display-lifecycle-not-reported"
    return "unknown"


@dataclass(frozen=True)
class VirtualDisplayLifecycle:
    width: int
    height: int
    dpi: int
    display_id: int

    def to_dict(self) -> dict[str, int]:
        return {
            "width": self.width,
            "height": self.height,
            "dpi": self.dpi,
            "displayId": self.display_id,
        }


def parse_new_display_line(line: str) -> VirtualDisplayLifecycle | None:
    match = _NEW_DISPLAY_RE.search(line)
    if not match:
        return None
    return VirtualDisplayLifecycle(
        width=int(match.group("width")),
        height=int(match.group("height")),
        dpi=int(match.group("dpi")),
        display_id=int(match.group("id")),
    )


def classify_application_log(line: str) -> tuple[str, str | None] | None:
    if _APP_ERROR_RE.search(line):
        return ("failed", None)
    match = _APP_START_RE.search(line)
    if match:
        return ("success", match.group("package"))
    return None


def virtual_display_capabilities(
    device: AndroidDevice,
    *,
    supported_codecs: list[str] | None = None,
    requested_package: str | None = None,
    package_installed: bool | None = None,
) -> dict[str, Any]:
    sdk = device.sdk or 0
    api_supported = sdk >= 29
    warnings: list[str] = []
    local_ime_supported = api_supported and not samsung_local_ime_policy_risk(device)
    if not api_supported:
        warnings.append("Virtual displays with secondary-display input require Android API 29 or newer.")
    if api_supported and not local_ime_supported:
        warnings.append(
            "Local virtual-display IME policy is disabled for this Samsung Android build; "
            "use default or fallback routing."
        )
    if requested_package and package_installed is False:
        warnings.append(f"Application is not installed: {requested_package}")
    codecs = supported_codecs or ["h264"]
    return {
        "virtualDisplaySupported": api_supported,
        "flexDisplaySupported": api_supported,
        "secondaryDisplayControlSupported": api_supported,
        "localImePolicySupported": local_ime_supported,
        "installedAppsQuerySupported": True,
        "requestedAppInstalled": package_installed,
        "requestedPackage": requested_package,
        "minimumApi": 29,
        "deviceApi": device.sdk,
        "supportedCodecs": codecs,
        "browserSupportedCodecs": ["h264"],
        "warnings": warnings,
    }
