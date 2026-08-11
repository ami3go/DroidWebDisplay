import type { BridgeTransport } from "@droid-web-display/scrcpy-protocol";
export type WebSocketFactory = (url: string) => WebSocket;
export declare class WebSocketBridgeTransport implements BridgeTransport {
    #private;
    readonly sessionId: string;
    private readonly baseUrl;
    private readonly socketFactory;
    constructor(sessionId: string, baseUrl?: string, socketFactory?: WebSocketFactory);
    openVideoChannel(): Promise<ReadableStream<Uint8Array>>;
    openAudioChannel(): Promise<ReadableStream<Uint8Array> | null>;
    openControlChannel(): Promise<ReadableWritablePair<Uint8Array, Uint8Array>>;
    close(): Promise<void>;
    private openReadableChannel;
    private openSocket;
}
