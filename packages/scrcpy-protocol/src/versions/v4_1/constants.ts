export const SCRCPY_VERSION = "4.1";
export const ADAPTER_ID = "scrcpy-4.1";
export const DEVICE_NAME_FIELD_LENGTH = 64;
export const PACKET_HEADER_LENGTH = 12;
export const PACKET_FLAG_SESSION = 1n << 63n;
export const PACKET_FLAG_CONFIG = 1n << 62n;
export const PACKET_FLAG_KEY_FRAME = 1n << 61n;
export const PACKET_PTS_MASK = PACKET_FLAG_KEY_FRAME - 1n;
export const CONTROL_MESSAGE_MAX_SIZE = 1 << 18;
export const DEVICE_MESSAGE_MAX_SIZE = 1 << 18;
export const INJECT_TEXT_MAX_LENGTH = 300;
export const CLIPBOARD_TEXT_MAX_LENGTH = CONTROL_MESSAGE_MAX_SIZE - 14;
export const SCAN_FILE_PATH_MAX_LENGTH = 256;

export const POINTER_ID_MOUSE = 0xffffffffffffffffn;
export const POINTER_ID_GENERIC_FINGER = 0xfffffffffffffffen;
export const POINTER_ID_VIRTUAL_FINGER = 0xfffffffffffffffdn;

export enum CodecId {
  Disabled = 0,
  ConfigurationError = 1,
  H264 = 0x68323634,
  H265 = 0x68323635,
  Av1 = 0x00617631,
  Vp8 = 0x00767038,
  Vp9 = 0x00767039,
  Opus = 0x6f707573,
  Aac = 0x00616163,
  Flac = 0x666c6163,
  Raw = 0x00726177,
}

export type SupportedCodecName = "h264" | "h265" | "av1" | "vp8" | "vp9" | "opus" | "aac" | "flac" | "raw";

export const CODEC_NAMES: Readonly<Record<number, SupportedCodecName>> = {
  [CodecId.H264]: "h264",
  [CodecId.H265]: "h265",
  [CodecId.Av1]: "av1",
  [CodecId.Vp8]: "vp8",
  [CodecId.Vp9]: "vp9",
  [CodecId.Opus]: "opus",
  [CodecId.Aac]: "aac",
  [CodecId.Flac]: "flac",
  [CodecId.Raw]: "raw",
};
