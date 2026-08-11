import { AsyncByteReader } from "../../common/async-byte-reader.js";
import type { MediaPacket, VideoSessionMeta } from "../../common/types.js";
import { type SupportedCodecName } from "./constants.js";
export interface MediaStreamHeader {
    readonly codecId: number;
    readonly codec: SupportedCodecName;
    readonly session?: VideoSessionMeta;
}
export interface MediaParserOptions {
    readonly kind: "video" | "audio";
    readonly maximumPacketSize?: number;
    readonly expectStreamMeta?: boolean;
    readonly fixedCodec?: SupportedCodecName;
}
export declare class ScrcpyMediaStreamParser {
    #private;
    constructor(reader: AsyncByteReader, options: MediaParserOptions);
    readHeader(): Promise<MediaStreamHeader>;
    readPacket(): Promise<MediaPacket>;
    packets(): AsyncGenerator<MediaPacket, never, void>;
}
