export function decoderBacklogAction(queueSize, threshold, decoderHasOutput, packetIsKeyFrame) {
    if (queueSize < threshold)
        return "decode";
    if (decoderHasOutput || packetIsKeyFrame)
        return "recover";
    return "drop-delta";
}
//# sourceMappingURL=video-backlog-policy.js.map