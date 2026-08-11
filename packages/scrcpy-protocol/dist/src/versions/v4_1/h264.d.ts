export interface H264DecoderConfiguration {
    readonly codec: string;
    readonly format: "annexb";
    readonly sequenceParameterSets: readonly Uint8Array[];
    readonly pictureParameterSets: readonly Uint8Array[];
}
export declare function extractH264DecoderConfiguration(data: Uint8Array): H264DecoderConfiguration;
export declare function splitAnnexBNalUnits(data: Uint8Array): Uint8Array[];
