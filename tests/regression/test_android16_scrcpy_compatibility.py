from droid_web_display.models import AndroidDevice
from droid_web_display.scrcpy.virtual_display import (
    classify_virtual_display_failure,
    virtual_display_capabilities,
)


def test_android16_display_listener_failure_is_classified() -> None:
    lines = [
        "java.lang.AbstractMethodError: Receiver class does not define or inherit an implementation",
        "android.view.IDisplayWindowListener.onDisplayAnimationsDisabledChanged",
    ]
    assert classify_virtual_display_failure(lines) == "android16-display-listener-incompatibility"


def test_android16_capability_probe_surfaces_upstream_warning() -> None:
    device = AndroidDevice(serial="test", state="device", manufacturer="Samsung", sdk=36)
    result = virtual_display_capabilities(device)
    assert any("Android 16" in warning for warning in result["warnings"])
    assert any("IDisplayWindowListener" in warning for warning in result["warnings"])


def test_unrelated_failure_keeps_existing_classification() -> None:
    assert classify_virtual_display_failure(["encoder failed"]) == "encoder-initialization-failed"
