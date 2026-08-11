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
export var CodecId;
(function (CodecId) {
    CodecId[CodecId["Disabled"] = 0] = "Disabled";
    CodecId[CodecId["ConfigurationError"] = 1] = "ConfigurationError";
    CodecId[CodecId["H264"] = 1748121140] = "H264";
    CodecId[CodecId["H265"] = 1748121141] = "H265";
    CodecId[CodecId["Av1"] = 6387249] = "Av1";
    CodecId[CodecId["Vp8"] = 7761976] = "Vp8";
    CodecId[CodecId["Vp9"] = 7761977] = "Vp9";
    CodecId[CodecId["Opus"] = 1869641075] = "Opus";
    CodecId[CodecId["Aac"] = 6381923] = "Aac";
    CodecId[CodecId["Flac"] = 1718378851] = "Flac";
    CodecId[CodecId["Raw"] = 7496055] = "Raw";
})(CodecId || (CodecId = {}));
export const CODEC_NAMES = {
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
//# sourceMappingURL=constants.js.map