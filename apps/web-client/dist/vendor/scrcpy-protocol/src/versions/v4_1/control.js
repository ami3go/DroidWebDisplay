import { CLIPBOARD_TEXT_MAX_LENGTH, CONTROL_MESSAGE_MAX_SIZE, INJECT_TEXT_MAX_LENGTH, SCAN_FILE_PATH_MAX_LENGTH, } from "./constants.js";
import { concatBytes, encodeLengthPrefixedUtf8, floatToI16Fixed, floatToU16Fixed, i16be, i32be, u16be, u32be, u64be, } from "../../common/binary.js";
import { InvalidProtocolValueError } from "../../common/errors.js";
export var ControlMessageType;
(function (ControlMessageType) {
    ControlMessageType[ControlMessageType["InjectKeycode"] = 0] = "InjectKeycode";
    ControlMessageType[ControlMessageType["InjectText"] = 1] = "InjectText";
    ControlMessageType[ControlMessageType["InjectTouchEvent"] = 2] = "InjectTouchEvent";
    ControlMessageType[ControlMessageType["InjectScrollEvent"] = 3] = "InjectScrollEvent";
    ControlMessageType[ControlMessageType["BackOrScreenOn"] = 4] = "BackOrScreenOn";
    ControlMessageType[ControlMessageType["ExpandNotificationPanel"] = 5] = "ExpandNotificationPanel";
    ControlMessageType[ControlMessageType["ExpandSettingsPanel"] = 6] = "ExpandSettingsPanel";
    ControlMessageType[ControlMessageType["CollapsePanels"] = 7] = "CollapsePanels";
    ControlMessageType[ControlMessageType["GetClipboard"] = 8] = "GetClipboard";
    ControlMessageType[ControlMessageType["SetClipboard"] = 9] = "SetClipboard";
    ControlMessageType[ControlMessageType["SetDisplayPower"] = 10] = "SetDisplayPower";
    ControlMessageType[ControlMessageType["RotateDevice"] = 11] = "RotateDevice";
    ControlMessageType[ControlMessageType["UhidCreate"] = 12] = "UhidCreate";
    ControlMessageType[ControlMessageType["UhidInput"] = 13] = "UhidInput";
    ControlMessageType[ControlMessageType["UhidDestroy"] = 14] = "UhidDestroy";
    ControlMessageType[ControlMessageType["OpenHardKeyboardSettings"] = 15] = "OpenHardKeyboardSettings";
    ControlMessageType[ControlMessageType["StartApp"] = 16] = "StartApp";
    ControlMessageType[ControlMessageType["ResetVideo"] = 17] = "ResetVideo";
    ControlMessageType[ControlMessageType["CameraSetTorch"] = 18] = "CameraSetTorch";
    ControlMessageType[ControlMessageType["CameraZoomIn"] = 19] = "CameraZoomIn";
    ControlMessageType[ControlMessageType["CameraZoomOut"] = 20] = "CameraZoomOut";
    ControlMessageType[ControlMessageType["ResizeDisplay"] = 21] = "ResizeDisplay";
    ControlMessageType[ControlMessageType["ScanFile"] = 22] = "ScanFile";
})(ControlMessageType || (ControlMessageType = {}));
export var CopyKey;
(function (CopyKey) {
    CopyKey[CopyKey["None"] = 0] = "None";
    CopyKey[CopyKey["Copy"] = 1] = "Copy";
    CopyKey[CopyKey["Cut"] = 2] = "Cut";
})(CopyKey || (CopyKey = {}));
export function serializeControlMessage(message) {
    const type = new Uint8Array([u8(message.type, "control message type")]);
    let result;
    switch (message.type) {
        case ControlMessageType.InjectKeycode:
            result = concatBytes(type, new Uint8Array([u8(message.action, "key action")]), i32be(message.keycode), u32be(message.repeat), i32be(message.metaState));
            break;
        case ControlMessageType.InjectText:
            result = concatBytes(type, encodeLengthPrefixedUtf8(message.text, INJECT_TEXT_MAX_LENGTH, 4));
            break;
        case ControlMessageType.InjectTouchEvent:
            result = concatBytes(type, new Uint8Array([u8(message.action, "touch action")]), u64be(message.pointerId), serializePosition(message.position), u16be(floatToU16Fixed(message.pressure)), i32be(message.actionButton), i32be(message.buttons));
            break;
        case ControlMessageType.InjectScrollEvent: {
            const horizontal = Math.max(-16, Math.min(16, message.horizontal)) / 16;
            const vertical = Math.max(-16, Math.min(16, message.vertical)) / 16;
            result = concatBytes(type, serializePosition(message.position), i16be(floatToI16Fixed(horizontal)), i16be(floatToI16Fixed(vertical)), i32be(message.buttons));
            break;
        }
        case ControlMessageType.BackOrScreenOn:
            result = concatBytes(type, new Uint8Array([u8(message.action, "back action")]));
            break;
        case ControlMessageType.GetClipboard:
            result = concatBytes(type, new Uint8Array([u8(message.copyKey, "copy key")]));
            break;
        case ControlMessageType.SetClipboard:
            result = concatBytes(type, u64be(message.sequence), new Uint8Array([message.paste ? 1 : 0]), encodeLengthPrefixedUtf8(message.text, CLIPBOARD_TEXT_MAX_LENGTH, 4));
            break;
        case ControlMessageType.SetDisplayPower:
            result = concatBytes(type, new Uint8Array([message.on ? 1 : 0]));
            break;
        case ControlMessageType.UhidCreate:
            if (message.reportDescriptor.byteLength > 0xffff) {
                throw new InvalidProtocolValueError("UHID report descriptor is too large");
            }
            result = concatBytes(type, u16be(message.id), u16be(message.vendorId), u16be(message.productId), encodeLengthPrefixedUtf8(message.name, 127, 1), u16be(message.reportDescriptor.byteLength), message.reportDescriptor);
            break;
        case ControlMessageType.UhidInput:
            if (message.data.byteLength > 0xffff) {
                throw new InvalidProtocolValueError("UHID input is too large");
            }
            result = concatBytes(type, u16be(message.id), u16be(message.data.byteLength), message.data);
            break;
        case ControlMessageType.UhidDestroy:
            result = concatBytes(type, u16be(message.id));
            break;
        case ControlMessageType.StartApp:
            result = concatBytes(type, encodeLengthPrefixedUtf8(message.name, 255, 1));
            break;
        case ControlMessageType.CameraSetTorch:
            result = concatBytes(type, new Uint8Array([message.on ? 1 : 0]));
            break;
        case ControlMessageType.ResizeDisplay:
            result = concatBytes(type, u16be(message.width), u16be(message.height));
            break;
        case ControlMessageType.ScanFile:
            result = concatBytes(type, encodeLengthPrefixedUtf8(message.path, SCAN_FILE_PATH_MAX_LENGTH, 4));
            break;
        case ControlMessageType.ExpandNotificationPanel:
        case ControlMessageType.ExpandSettingsPanel:
        case ControlMessageType.CollapsePanels:
        case ControlMessageType.RotateDevice:
        case ControlMessageType.OpenHardKeyboardSettings:
        case ControlMessageType.ResetVideo:
        case ControlMessageType.CameraZoomIn:
        case ControlMessageType.CameraZoomOut:
            result = type;
            break;
        default:
            throw new InvalidProtocolValueError(`unknown scrcpy control message type: ${message.type}`);
    }
    if (result.byteLength > CONTROL_MESSAGE_MAX_SIZE) {
        throw new InvalidProtocolValueError(`control message exceeds ${CONTROL_MESSAGE_MAX_SIZE} bytes`);
    }
    return result;
}
function serializePosition(position) {
    if (position.screenWidth < 0 || position.screenHeight < 0 || position.screenWidth > 0xffff || position.screenHeight > 0xffff) {
        throw new InvalidProtocolValueError("screen dimensions must fit uint16");
    }
    return concatBytes(i32be(position.x), i32be(position.y), u16be(position.screenWidth), u16be(position.screenHeight));
}
function u8(value, label) {
    if (!Number.isInteger(value) || value < 0 || value > 0xff) {
        throw new InvalidProtocolValueError(`${label} must fit uint8: ${value}`);
    }
    return value;
}
//# sourceMappingURL=control.js.map