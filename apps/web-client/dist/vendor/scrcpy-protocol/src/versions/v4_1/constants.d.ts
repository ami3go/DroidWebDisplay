export declare const SCRCPY_VERSION = "4.1";
export declare const ADAPTER_ID = "scrcpy-4.1";
export declare const DEVICE_NAME_FIELD_LENGTH = 64;
export declare const PACKET_HEADER_LENGTH = 12;
export declare const PACKET_FLAG_SESSION: bigint;
export declare const PACKET_FLAG_CONFIG: bigint;
export declare const PACKET_FLAG_KEY_FRAME: bigint;
export declare const PACKET_PTS_MASK: bigint;
export declare const CONTROL_MESSAGE_MAX_SIZE: number;
export declare const DEVICE_MESSAGE_MAX_SIZE: number;
export declare const INJECT_TEXT_MAX_LENGTH = 300;
export declare const CLIPBOARD_TEXT_MAX_LENGTH: number;
export declare const SCAN_FILE_PATH_MAX_LENGTH = 256;
export declare const POINTER_ID_MOUSE = 18446744073709551615n;
export declare const POINTER_ID_GENERIC_FINGER = 18446744073709551614n;
export declare const POINTER_ID_VIRTUAL_FINGER = 18446744073709551613n;
export declare enum CodecId {
    Disabled = 0,
    ConfigurationError = 1,
    H264 = 1748121140,
    H265 = 1748121141,
    Av1 = 6387249,
    Vp8 = 7761976,
    Vp9 = 7761977,
    Opus = 1869641075,
    Aac = 6381923,
    Flac = 1718378851,
    Raw = 7496055
}
export type SupportedCodecName = "h264" | "h265" | "av1" | "vp8" | "vp9" | "opus" | "aac" | "flac" | "raw";
export declare const CODEC_NAMES: Readonly<Record<number, SupportedCodecName>>;
