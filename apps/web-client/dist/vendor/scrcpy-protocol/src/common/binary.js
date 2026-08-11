import { InvalidProtocolValueError } from "./errors.js";
export function concatBytes(...parts) {
    const length = parts.reduce((total, part) => total + part.byteLength, 0);
    const result = new Uint8Array(length);
    let offset = 0;
    for (const part of parts) {
        result.set(part, offset);
        offset += part.byteLength;
    }
    return result;
}
export function u16be(value) {
    assertIntegerRange(value, 0, 0xffff, "uint16");
    const result = new Uint8Array(2);
    new DataView(result.buffer).setUint16(0, value, false);
    return result;
}
export function i16be(value) {
    assertIntegerRange(value, -0x8000, 0x7fff, "int16");
    const result = new Uint8Array(2);
    new DataView(result.buffer).setInt16(0, value, false);
    return result;
}
export function u32be(value) {
    assertIntegerRange(value, 0, 0xffffffff, "uint32");
    const result = new Uint8Array(4);
    new DataView(result.buffer).setUint32(0, value, false);
    return result;
}
export function i32be(value) {
    assertIntegerRange(value, -0x80000000, 0x7fffffff, "int32");
    const result = new Uint8Array(4);
    new DataView(result.buffer).setInt32(0, value, false);
    return result;
}
export function u64be(value) {
    if (value < 0n || value > 0xffffffffffffffffn) {
        throw new InvalidProtocolValueError(`uint64 out of range: ${value}`);
    }
    const result = new Uint8Array(8);
    new DataView(result.buffer).setBigUint64(0, value, false);
    return result;
}
export function readU16be(data, offset = 0) {
    return view(data, offset, 2).getUint16(0, false);
}
export function readI16be(data, offset = 0) {
    return view(data, offset, 2).getInt16(0, false);
}
export function readU32be(data, offset = 0) {
    return view(data, offset, 4).getUint32(0, false);
}
export function readI32be(data, offset = 0) {
    return view(data, offset, 4).getInt32(0, false);
}
export function readU64be(data, offset = 0) {
    return view(data, offset, 8).getBigUint64(0, false);
}
function view(data, offset, length) {
    if (offset < 0 || length < 0 || offset + length > data.byteLength) {
        throw new RangeError(`binary read out of bounds: offset=${offset}, length=${length}, available=${data.byteLength}`);
    }
    return new DataView(data.buffer, data.byteOffset + offset, length);
}
export function encodeUtf8Truncated(text, maxBytes) {
    if (!Number.isInteger(maxBytes) || maxBytes < 0) {
        throw new InvalidProtocolValueError(`invalid UTF-8 maximum length: ${maxBytes}`);
    }
    const encoder = new TextEncoder();
    const full = encoder.encode(text);
    if (full.byteLength <= maxBytes) {
        return full;
    }
    let used = 0;
    let result = "";
    for (const codePoint of text) {
        const encoded = encoder.encode(codePoint);
        if (used + encoded.byteLength > maxBytes) {
            break;
        }
        result += codePoint;
        used += encoded.byteLength;
    }
    return encoder.encode(result);
}
export function encodeLengthPrefixedUtf8(text, maxBytes, sizeBytes) {
    const encoded = encodeUtf8Truncated(text, maxBytes);
    const maxLength = 2 ** (8 * sizeBytes) - 1;
    if (encoded.byteLength > maxLength) {
        throw new InvalidProtocolValueError(`string does not fit a ${sizeBytes}-byte length prefix`);
    }
    const prefix = new Uint8Array(sizeBytes);
    const dataView = new DataView(prefix.buffer);
    if (sizeBytes === 1) {
        dataView.setUint8(0, encoded.byteLength);
    }
    else if (sizeBytes === 2) {
        dataView.setUint16(0, encoded.byteLength, false);
    }
    else {
        dataView.setUint32(0, encoded.byteLength, false);
    }
    return concatBytes(prefix, encoded);
}
export function floatToU16Fixed(value) {
    if (!Number.isFinite(value) || value < 0 || value > 1) {
        throw new InvalidProtocolValueError(`unsigned fixed-point value must be in [0, 1]: ${value}`);
    }
    const scaled = Math.trunc(value * 0x10000);
    return scaled >= 0xffff ? 0xffff : scaled;
}
export function floatToI16Fixed(value) {
    if (!Number.isFinite(value) || value < -1 || value > 1) {
        throw new InvalidProtocolValueError(`signed fixed-point value must be in [-1, 1]: ${value}`);
    }
    const scaled = Math.trunc(value * 0x8000);
    return scaled >= 0x7fff ? 0x7fff : scaled;
}
function assertIntegerRange(value, minimum, maximum, label) {
    if (!Number.isInteger(value) || value < minimum || value > maximum) {
        throw new InvalidProtocolValueError(`${label} out of range: ${value}`);
    }
}
//# sourceMappingURL=binary.js.map