export type DecoderBacklogAction = "decode" | "drop-delta" | "recover";

export function decoderBacklogAction(
  queueSize: number,
  threshold: number,
  decoderHasOutput: boolean,
  packetIsKeyFrame: boolean,
): DecoderBacklogAction {
  if (queueSize < threshold) return "decode";
  if (decoderHasOutput || packetIsKeyFrame) return "recover";
  return "drop-delta";
}
