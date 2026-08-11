import { InvalidProtocolValueError } from "../../common/errors.js";
import { DEVICE_NAME_FIELD_LENGTH } from "./constants.js";
export async function readDummyByte(reader) {
    const value = await reader.readU8();
    if (value !== 0) {
        throw new InvalidProtocolValueError(`unexpected scrcpy dummy byte: ${value}`);
    }
}
export async function readDeviceInfo(reader) {
    const field = await reader.readExactly(DEVICE_NAME_FIELD_LENGTH);
    const terminator = field.indexOf(0);
    const nameBytes = terminator === -1 ? field : field.slice(0, terminator);
    return { name: new TextDecoder("utf-8", { fatal: true }).decode(nameBytes) };
}
//# sourceMappingURL=handshake.js.map