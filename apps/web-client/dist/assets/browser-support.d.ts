export interface BrowserCapabilityReport {
    readonly supported: boolean;
    readonly missing: readonly string[];
    readonly userAgent: string;
    readonly audioSupported: boolean;
    readonly missingAudio: readonly string[];
}
export interface BrowserCapabilityScope {
    readonly WebSocket?: unknown;
    readonly ReadableStream?: unknown;
    readonly WritableStream?: unknown;
    readonly VideoDecoder?: unknown;
    readonly EncodedVideoChunk?: unknown;
    readonly AudioDecoder?: unknown;
    readonly EncodedAudioChunk?: unknown;
    readonly AudioContext?: unknown;
    readonly navigator?: {
        readonly userAgent?: string;
    };
}
export declare function inspectBrowserCapabilities(scope?: BrowserCapabilityScope): BrowserCapabilityReport;
