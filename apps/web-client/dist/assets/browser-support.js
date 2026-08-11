export function inspectBrowserCapabilities(scope = globalThis) {
    const required = ["WebSocket", "ReadableStream", "WritableStream", "VideoDecoder", "EncodedVideoChunk"];
    const missing = required.filter((name) => typeof scope[name] === "undefined");
    const audio = ["AudioDecoder", "EncodedAudioChunk", "AudioContext"];
    const missingAudio = audio.filter((name) => typeof scope[name] === "undefined");
    return {
        supported: missing.length === 0,
        missing,
        userAgent: scope.navigator?.userAgent ?? "unknown",
        audioSupported: missingAudio.length === 0,
        missingAudio,
    };
}
//# sourceMappingURL=browser-support.js.map