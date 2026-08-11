export declare class ScrcpyProtocolError extends Error {
    constructor(message: string, options?: ErrorOptions);
}
export declare class TruncatedStreamError extends ScrcpyProtocolError {
}
export declare class InvalidProtocolValueError extends ScrcpyProtocolError {
}
export declare class UnsupportedCodecError extends ScrcpyProtocolError {
}
export declare class StreamDisabledError extends ScrcpyProtocolError {
    readonly configurationError: boolean;
    constructor(configurationError: boolean);
}
export declare class VersionMismatchError extends ScrcpyProtocolError {
}
