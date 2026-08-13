export type DecoderBacklogAction = "decode" | "drop-delta" | "recover";
export declare function decoderBacklogAction(queueSize: number, threshold: number, decoderHasOutput: boolean, packetIsKeyFrame: boolean): DecoderBacklogAction;
