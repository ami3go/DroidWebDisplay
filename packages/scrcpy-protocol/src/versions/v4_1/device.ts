import { AsyncByteReader } from "../../common/async-byte-reader.js";
import { InvalidProtocolValueError } from "../../common/errors.js";
import { DEVICE_MESSAGE_MAX_SIZE } from "./constants.js";

export enum DeviceMessageType {
  Clipboard = 0,
  AckClipboard = 1,
  UhidOutput = 2,
}

export type DeviceMessage =
  | { readonly type: DeviceMessageType.Clipboard; readonly text: string }
  | { readonly type: DeviceMessageType.AckClipboard; readonly sequence: bigint }
  | { readonly type: DeviceMessageType.UhidOutput; readonly id: number; readonly data: Uint8Array };

export class DeviceMessageParser {
  public constructor(private readonly reader: AsyncByteReader) {}

  public async read(): Promise<DeviceMessage> {
    const type = await this.reader.readU8();
    switch (type) {
      case DeviceMessageType.Clipboard: {
        const length = await this.reader.readU32();
        ensurePayloadLength(length, 5);
        const text = new TextDecoder("utf-8", { fatal: true }).decode(await this.reader.readExactly(length));
        return { type, text };
      }
      case DeviceMessageType.AckClipboard:
        return { type, sequence: await this.reader.readU64() };
      case DeviceMessageType.UhidOutput: {
        const id = await this.reader.readU16();
        const length = await this.reader.readU16();
        ensurePayloadLength(length, 5);
        return { type, id, data: await this.reader.readExactly(length) };
      }
      default:
        throw new InvalidProtocolValueError(`unknown scrcpy device message type: ${type}`);
    }
  }

  public async *messages(): AsyncGenerator<DeviceMessage, never, void> {
    while (true) {
      yield await this.read();
    }
  }
}

function ensurePayloadLength(length: number, headerLength: number): void {
  if (length > DEVICE_MESSAGE_MAX_SIZE - headerLength) {
    throw new InvalidProtocolValueError(`device message payload ${length} exceeds maximum`);
  }
}
