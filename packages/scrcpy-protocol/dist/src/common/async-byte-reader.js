import { TruncatedStreamError } from "./errors.js";
import { readU16be, readU32be, readU64be } from "./binary.js";
export class AsyncByteReader {
    #reader;
    #label;
    #maximumBufferedBytes;
    #buffer = new Uint8Array(0);
    #ended = false;
    #bytesRead = 0;
    constructor(stream, options = {}) {
        this.#reader = stream.getReader();
        this.#label = options.label ?? "scrcpy stream";
        this.#maximumBufferedBytes = options.maximumBufferedBytes ?? 64 * 1024 * 1024;
    }
    get bytesRead() {
        return this.#bytesRead;
    }
    async readExactly(length) {
        if (!Number.isInteger(length) || length < 0) {
            throw new RangeError(`invalid read length: ${length}`);
        }
        while (this.#buffer.byteLength < length && !this.#ended) {
            const result = await this.#reader.read();
            if (result.done) {
                this.#ended = true;
                break;
            }
            if (!(result.value instanceof Uint8Array)) {
                throw new TypeError(`${this.#label} produced a non-Uint8Array chunk`);
            }
            if (result.value.byteLength === 0) {
                continue;
            }
            const combinedLength = this.#buffer.byteLength + result.value.byteLength;
            if (combinedLength > this.#maximumBufferedBytes) {
                throw new RangeError(`${this.#label} exceeded ${this.#maximumBufferedBytes} buffered bytes`);
            }
            const combined = new Uint8Array(combinedLength);
            combined.set(this.#buffer);
            combined.set(result.value, this.#buffer.byteLength);
            this.#buffer = combined;
        }
        if (this.#buffer.byteLength < length) {
            throw new TruncatedStreamError(`${this.#label} ended after ${this.#bytesRead + this.#buffer.byteLength} bytes; ` +
                `${length - this.#buffer.byteLength} more bytes were required`);
        }
        const result = this.#buffer.slice(0, length);
        this.#buffer = this.#buffer.slice(length);
        this.#bytesRead += length;
        return result;
    }
    async readU8() {
        return (await this.readExactly(1))[0];
    }
    async readU16() {
        return readU16be(await this.readExactly(2));
    }
    async readU32() {
        return readU32be(await this.readExactly(4));
    }
    async readU64() {
        return readU64be(await this.readExactly(8));
    }
    async cancel(reason) {
        await this.#reader.cancel(reason);
    }
}
//# sourceMappingURL=async-byte-reader.js.map