export class ScrcpyProtocolError extends Error {
    constructor(message, options) {
        super(message, options);
        this.name = new.target.name;
    }
}
export class TruncatedStreamError extends ScrcpyProtocolError {
}
export class InvalidProtocolValueError extends ScrcpyProtocolError {
}
export class UnsupportedCodecError extends ScrcpyProtocolError {
}
export class StreamDisabledError extends ScrcpyProtocolError {
    configurationError;
    constructor(configurationError) {
        super(configurationError
            ? "scrcpy stream was disabled because of a device configuration error"
            : "scrcpy stream was explicitly disabled by the device");
        this.configurationError = configurationError;
    }
}
export class VersionMismatchError extends ScrcpyProtocolError {
}
//# sourceMappingURL=errors.js.map