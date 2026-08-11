import { InvalidProtocolValueError } from "../../common/errors.js";
import { DEVICE_MESSAGE_MAX_SIZE } from "./constants.js";
export var DeviceMessageType;
(function (DeviceMessageType) {
    DeviceMessageType[DeviceMessageType["Clipboard"] = 0] = "Clipboard";
    DeviceMessageType[DeviceMessageType["AckClipboard"] = 1] = "AckClipboard";
    DeviceMessageType[DeviceMessageType["UhidOutput"] = 2] = "UhidOutput";
})(DeviceMessageType || (DeviceMessageType = {}));
export class DeviceMessageParser {
    reader;
    constructor(reader) {
        this.reader = reader;
    }
    async read() {
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
    async *messages() {
        while (true) {
            yield await this.read();
        }
    }
}
function ensurePayloadLength(length, headerLength) {
    if (length > DEVICE_MESSAGE_MAX_SIZE - headerLength) {
        throw new InvalidProtocolValueError(`device message payload ${length} exceeds maximum`);
    }
}
//# sourceMappingURL=device.js.map