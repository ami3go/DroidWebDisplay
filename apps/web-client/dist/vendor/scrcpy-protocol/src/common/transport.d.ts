export interface BridgeTransport {
    readonly sessionId: string;
    openVideoChannel(): Promise<ReadableStream<Uint8Array>>;
    openAudioChannel(): Promise<ReadableStream<Uint8Array> | null>;
    openControlChannel(): Promise<ReadableWritablePair<Uint8Array, Uint8Array>>;
    close(): Promise<void>;
}
export interface SessionOptions {
    readonly video: boolean;
    readonly audio: boolean;
    readonly control: boolean;
    readonly expectDummyByte?: boolean;
    readonly expectDeviceMeta?: boolean;
    readonly expectStreamMeta?: boolean;
}
export interface CompatibilityResult {
    readonly compatible: boolean;
    readonly reason?: string;
}
export interface ServerInfo {
    readonly scrcpyVersion: string;
    readonly adapterId: string;
}
