from __future__ import annotations

from droid_web_display.models import AndroidDevice, DeviceState

KNOWN_STATES = {state.value for state in DeviceState if state is not DeviceState.UNKNOWN}


def _connection_type(serial: str, fields: dict[str, str]) -> str:
    if "usb" in fields:
        return "usb"
    if serial.startswith("emulator-"):
        return "emulator"
    if ":" in serial:
        return "tcpip"
    return "unknown"


def parse_adb_devices(output: str) -> list[AndroidDevice]:
    """Parse ``adb devices -l`` without assuming serials contain no spaces.

    scrcpy parses device lines from right to left because Android permits serial
    values containing spaces. This implementation follows the same strategy.
    """

    lines = output.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    header_seen = False
    devices: list[AndroidDevice] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not header_seen:
            if line.startswith("List of devices attached"):
                header_seen = True
            continue
        if not line or line.startswith("*") or line.startswith("adb server"):
            continue

        tokens = line.split()
        state_index: int | None = None
        for index in range(len(tokens) - 1, -1, -1):
            if tokens[index] in KNOWN_STATES:
                state_index = index
                break
        if state_index is None or state_index == 0:
            continue

        serial = " ".join(tokens[:state_index]).strip()
        state = tokens[state_index]
        if not serial:
            continue

        fields: dict[str, str] = {}
        for token in tokens[state_index + 1 :]:
            if ":" not in token:
                continue
            key, value = token.split(":", 1)
            if key and value:
                fields[key] = value

        devices.append(
            AndroidDevice(
                serial=serial,
                state=state,
                model=fields.get("model"),
                product=fields.get("product"),
                device=fields.get("device"),
                transport_id=fields.get("transport_id"),
                usb=fields.get("usb"),
                connection_type=_connection_type(serial, fields),
                metadata=fields,
            )
        )

    return devices
