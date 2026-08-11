export class ScrcpyProtocolError extends Error {
  public constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = new.target.name;
  }
}

export class TruncatedStreamError extends ScrcpyProtocolError {}
export class InvalidProtocolValueError extends ScrcpyProtocolError {}
export class UnsupportedCodecError extends ScrcpyProtocolError {}
export class StreamDisabledError extends ScrcpyProtocolError {
  public constructor(public readonly configurationError: boolean) {
    super(configurationError
      ? "scrcpy stream was disabled because of a device configuration error"
      : "scrcpy stream was explicitly disabled by the device");
  }
}
export class VersionMismatchError extends ScrcpyProtocolError {}
