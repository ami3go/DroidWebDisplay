import { AsyncByteReader } from "../../common/async-byte-reader.js";
export declare enum DeviceMessageType {
    Clipboard = 0,
    AckClipboard = 1,
    UhidOutput = 2
}
export type DeviceMessage = {
    readonly type: DeviceMessageType.Clipboard;
    readonly text: string;
} | {
    readonly type: DeviceMessageType.AckClipboard;
    readonly sequence: bigint;
} | {
    readonly type: DeviceMessageType.UhidOutput;
    readonly id: number;
    readonly data: Uint8Array;
};
export declare class DeviceMessageParser {
    private readonly reader;
    constructor(reader: AsyncByteReader);
    read(): Promise<DeviceMessage>;
    messages(): AsyncGenerator<DeviceMessage, never, void>;
}
