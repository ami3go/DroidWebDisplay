export type DecoderBacklogAction = "decode" | "drop-delta" | "recover";

const MIN_RECOVERY_THRESHOLD = 12;

export function decoderBacklogAction(
  queueSize: number,
  threshold: number,
  _decoderHasOutput: boolean,
  packetIsKeyFrame: boolean,
): DecoderBacklogAction {
  // Four queued frames at 60 fps is only ~67 ms and is too small a margin for
  // normal browser/decoder jitter. Never treat a backlog smaller than twelve
  // frames (~200 ms at 60 fps) as a reason to recover the decoder.
  const effectiveThreshold = Math.max(threshold, MIN_RECOVERY_THRESHOLD);
  if (queueSize < effectiveThreshold) return "decode";

  // Resetting WebCodecs while the current packet is a delta frame leaves the
  // renderer unable to decode again until a future H.264 keyframe arrives.
  // Preserve the existing decoder state and shed incoming delta frames instead.
  // A keyframe is safe to use as the first packet after a local decoder reset.
  if (packetIsKeyFrame) return "recover";
  return "drop-delta";
}
