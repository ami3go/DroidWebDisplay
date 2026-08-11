from droid_web_display.adb.devices import parse_adb_devices


def test_parse_devices_states_and_metadata() -> None:
    output = """* daemon started successfully
List of devices attached
ABC123\tdevice usb:1-2 product:foo model:Pixel_8 device:husky transport_id:3
XYZ999\tunauthorized usb:2-1 transport_id:4
192.168.0.5:5555\toffline product:bar model:Tablet device:tab transport_id:5

"""
    devices = parse_adb_devices(output)
    assert [device.serial for device in devices] == ["ABC123", "XYZ999", "192.168.0.5:5555"]
    assert devices[0].ready is True
    assert devices[0].model == "Pixel_8"
    assert devices[0].connection_type == "usb"
    assert devices[1].authorization_required is True
    assert devices[2].connection_type == "tcpip"


def test_parse_serial_containing_spaces_from_right() -> None:
    output = """List of devices attached
serial with spaces device usb:3-1 model:Odd_Device transport_id:7
"""
    devices = parse_adb_devices(output)
    assert len(devices) == 1
    assert devices[0].serial == "serial with spaces"
    assert devices[0].state == "device"
