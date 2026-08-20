export function browserName(userAgent) {
    const matchers = [
        [/Edg\/([0-9.]+)/, "Edge"],
        [/Chrome\/([0-9.]+)/, "Chrome"],
        [/Firefox\/([0-9.]+)/, "Firefox"],
        [/Version\/([0-9.]+).*Safari\//, "Safari"],
    ];
    for (const [pattern, name] of matchers) {
        const match = pattern.exec(userAgent);
        if (match)
            return `${name} ${match[1]}`;
    }
    return userAgent === "unknown" ? "unknown" : "Other browser";
}
export function inspectBrowserCapabilities(scope = globalThis) {
    const required = ["WebSocket", "ReadableStream", "WritableStream", "VideoDecoder", "EncodedVideoChunk"];
    const missing = required.filter((name) => typeof scope[name] === "undefined");
    const audio = ["AudioDecoder", "EncodedAudioChunk", "AudioContext"];
    const missingAudio = audio.filter((name) => typeof scope[name] === "undefined");
    const userAgent = scope.navigator?.userAgent ?? "unknown";
    const concurrency = scope.navigator?.hardwareConcurrency;
    return {
        supported: missing.length === 0,
        missing,
        userAgent,
        browserName: browserName(userAgent),
        platform: scope.navigator?.platform || "unknown",
        hardwareConcurrency: typeof concurrency === "number" && Number.isFinite(concurrency) ? concurrency : null,
        audioSupported: missingAudio.length === 0,
        missingAudio,
    };
}
//# sourceMappingURL=browser-support.js.map