import {
  CLIPBOARD_TEXT_MAX_LENGTH,
  CONTROL_MESSAGE_MAX_SIZE,
  INJECT_TEXT_MAX_LENGTH,
  SCAN_FILE_PATH_MAX_LENGTH,
} from "./constants.js";
import {
  concatBytes,
  encodeLengthPrefixedUtf8,
  floatToI16Fixed,
  floatToU16Fixed,
  i16be,
  i32be,
  u16be,
  u32be,
  u64be,
} from "../../common/binary.js";
import { InvalidProtocolValueError } from "../../common/errors.js";
import type { Position } from "../../common/types.js";

export enum ControlMessageType {
  InjectKeycode = 0,
  InjectText = 1,
  InjectTouchEvent = 2,
  InjectScrollEvent = 3,
  BackOrScreenOn = 4,
  ExpandNotificationPanel = 5,
  ExpandSettingsPanel = 6,
  CollapsePanels = 7,
  GetClipboard = 8,
  SetClipboard = 9,
  SetDisplayPower = 10,
  RotateDevice = 11,
  UhidCreate = 12,
  UhidInput = 13,
  UhidDestroy = 14,
  OpenHardKeyboardSettings = 15,
  StartApp = 16,
  ResetVideo = 17,
  CameraSetTorch = 18,
  CameraZoomIn = 19,
  CameraZoomOut = 20,
  ResizeDisplay = 21,
  ScanFile = 22,
}

export enum CopyKey {
  None = 0,
  Copy = 1,
  Cut = 2,
}

export type ControlMessage =
  | { readonly type: ControlMessageType.InjectKeycode; readonly action: number; readonly keycode: number; readonly repeat: number; readonly metaState: number }
  | { readonly type: ControlMessageType.InjectText; readonly text: string }
  | { readonly type: ControlMessageType.InjectTouchEvent; readonly action: number; readonly pointerId: bigint; readonly position: Position; readonly pressure: number; readonly actionButton: number; readonly buttons: number }
  | { readonly type: ControlMessageType.InjectScrollEvent; readonly position: Position; readonly horizontal: number; readonly vertical: number; readonly buttons: number }
  | { readonly type: ControlMessageType.BackOrScreenOn; readonly action: number }
  | { readonly type: ControlMessageType.GetClipboard; readonly copyKey: CopyKey }
  | { readonly type: ControlMessageType.SetClipboard; readonly sequence: bigint; readonly paste: boolean; readonly text: string }
  | { readonly type: ControlMessageType.SetDisplayPower; readonly on: boolean }
  | { readonly type: ControlMessageType.UhidCreate; readonly id: number; readonly vendorId: number; readonly productId: number; readonly name: string; readonly reportDescriptor: Uint8Array }
  | { readonly type: ControlMessageType.UhidInput; readonly id: number; readonly data: Uint8Array }
  | { readonly type: ControlMessageType.UhidDestroy; readonly id: number }
  | { readonly type: ControlMessageType.StartApp; readonly name: string }
  | { readonly type: ControlMessageType.CameraSetTorch; readonly on: boolean }
  | { readonly type: ControlMessageType.ResizeDisplay; readonly width: number; readonly height: number }
  | { readonly type: ControlMessageType.ScanFile; readonly path: string }
  | { readonly type: EmptyControlMessageType };

export type EmptyControlMessageType =
  | ControlMessageType.ExpandNotificationPanel
  | ControlMessageType.ExpandSettingsPanel
  | ControlMessageType.CollapsePanels
  | ControlMessageType.RotateDevice
  | ControlMessageType.OpenHardKeyboardSettings
  | ControlMessageType.ResetVideo
  | ControlMessageType.CameraZoomIn
  | ControlMessageType.CameraZoomOut;

export function serializeControlMessage(message: ControlMessage): Uint8Array {
  const type = new Uint8Array([u8(message.type, "control message type")]);
  let result: Uint8Array;
  switch (message.type) {
    case ControlMessageType.InjectKeycode:
      result = concatBytes(type, new Uint8Array([u8(message.action, "key action")]), i32be(message.keycode), u32be(message.repeat), i32be(message.metaState));
      break;
    case ControlMessageType.InjectText:
      result = concatBytes(type, encodeLengthPrefixedUtf8(message.text, INJECT_TEXT_MAX_LENGTH, 4));
      break;
    case ControlMessageType.InjectTouchEvent:
      result = concatBytes(
        type,
        new Uint8Array([u8(message.action, "touch action")]),
        u64be(message.pointerId),
        serializePosition(message.position),
        u16be(floatToU16Fixed(message.pressure)),
        i32be(message.actionButton),
        i32be(message.buttons),
      );
      break;
    case ControlMessageType.InjectScrollEvent: {
      const horizontal = Math.max(-16, Math.min(16, message.horizontal)) / 16;
      const vertical = Math.max(-16, Math.min(16, message.vertical)) / 16;
      result = concatBytes(
        type,
        serializePosition(message.position),
        i16be(floatToI16Fixed(horizontal)),
        i16be(floatToI16Fixed(vertical)),
        i32be(message.buttons),
      );
      break;
    }
    case ControlMessageType.BackOrScreenOn:
      result = concatBytes(type, new Uint8Array([u8(message.action, "back action")]));
      break;
    case ControlMessageType.GetClipboard:
      result = concatBytes(type, new Uint8Array([u8(message.copyKey, "copy key")]));
      break;
    case ControlMessageType.SetClipboard:
      result = concatBytes(
        type,
        u64be(message.sequence),
        new Uint8Array([message.paste ? 1 : 0]),
        encodeLengthPrefixedUtf8(message.text, CLIPBOARD_TEXT_MAX_LENGTH, 4),
      );
      break;
    case ControlMessageType.SetDisplayPower:
      result = concatBytes(type, new Uint8Array([message.on ? 1 : 0]));
      break;
    case ControlMessageType.UhidCreate:
      if (message.reportDescriptor.byteLength > 0xffff) {
        throw new InvalidProtocolValueError("UHID report descriptor is too large");
      }
      result = concatBytes(
        type,
        u16be(message.id),
        u16be(message.vendorId),
        u16be(message.productId),
        encodeLengthPrefixedUtf8(message.name, 127, 1),
        u16be(message.reportDescriptor.byteLength),
        message.reportDescriptor,
      );
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
      throw new InvalidProtocolValueError(`unknown scrcpy control message type: ${(message as { type: number }).type}`);
  }
  if (result.byteLength > CONTROL_MESSAGE_MAX_SIZE) {
    throw new InvalidProtocolValueError(`control message exceeds ${CONTROL_MESSAGE_MAX_SIZE} bytes`);
  }
  return result;
}

function serializePosition(position: Position): Uint8Array {
  if (position.screenWidth < 0 || position.screenHeight < 0 || position.screenWidth > 0xffff || position.screenHeight > 0xffff) {
    throw new InvalidProtocolValueError("screen dimensions must fit uint16");
  }
  return concatBytes(i32be(position.x), i32be(position.y), u16be(position.screenWidth), u16be(position.screenHeight));
}

function u8(value: number, label: string): number {
  if (!Number.isInteger(value) || value < 0 || value > 0xff) {
    throw new InvalidProtocolValueError(`${label} must fit uint8: ${value}`);
  }
  return value;
}
