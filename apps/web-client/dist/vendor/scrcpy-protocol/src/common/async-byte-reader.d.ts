export interface ByteReaderOptions {
    readonly label?: string;
    readonly maximumBufferedBytes?: number;
}
export declare class AsyncByteReader {
    #private;
    constructor(stream: ReadableStream<Uint8Array>, options?: ByteReaderOptions);
    get bytesRead(): number;
    readExactly(length: number): Promise<Uint8Array>;
    readU8(): Promise<number>;
    readU16(): Promise<number>;
    readU32(): Promise<number>;
    readU64(): Promise<bigint>;
    cancel(reason?: unknown): Promise<void>;
}
