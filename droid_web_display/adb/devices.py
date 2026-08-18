from __future__ import annotations

from droid_web_display.models import AndroidDevice, DeviceState

KNOWN_STATES = {state.value for state in DeviceState if state is not DeviceState.UNKNOWN}
# States keyed by their token tuple. adb reports some of them as a phrase
# followed by free-text advice, e.g. "no permissions (user in plugdev group;
# are your udev rules wrong?); see [...]" — those must still surface as devices
# so the UI can explain why they are unusable.
_STATE_PHRASES = {tuple(value.split()): value for value in KNOWN_STATES}
_WIDEST_PHRASE = max(len(parts) for parts in _STATE_PHRASES)


def _locate_state(tokens: list[str]) -> tuple[int, str, int] | None:
    """Return (serial_end, state, fields_start) for a device line.

    Scans right to left so the rightmost state token wins, which is what
    separates a serial containing spaces from the state that follows it. At
    each position the widest phrase is tried first, so "no permissions" is
    never mistaken for a bare "permissions".
    """
    lowered = [token.lower() for token in tokens]
    for index in range(len(tokens) - 1, -1, -1):
        for width in range(min(_WIDEST_PHRASE, len(tokens) - index), 0, -1):
            state = _STATE_PHRASES.get(tuple(lowered[index : index + width]))
            if state is not None:
                return index, state, index + width
    return None


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
        located = _locate_state(tokens)
        if located is None:
            continue
        state_index, state, fields_start = located
        if state_index == 0:
            continue

        serial = " ".join(tokens[:state_index]).strip()
        if not serial:
            continue

        fields: dict[str, str] = {}
        for token in tokens[fields_start:]:
            if ":" not in token:
                continue
            key, value = token.split(":", 1)
            # Skip the free-text advice adb appends after some states, which
            # contains colons ("see [http://...]") but no key:value pairs.
            if key and value and key.replace("_", "").isalnum():
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
