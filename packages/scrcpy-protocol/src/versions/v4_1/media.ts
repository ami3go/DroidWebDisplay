import { AsyncByteReader } from "../../common/async-byte-reader.js";
import { InvalidProtocolValueError, StreamDisabledError, UnsupportedCodecError } from "../../common/errors.js";
import { readU32be, readU64be } from "../../common/binary.js";
import type { MediaPacket, VideoSessionMeta } from "../../common/types.js";
import {
  CODEC_NAMES,
  CodecId,
  PACKET_FLAG_CONFIG,
  PACKET_FLAG_KEY_FRAME,
  PACKET_FLAG_SESSION,
  PACKET_HEADER_LENGTH,
  PACKET_PTS_MASK,
  type SupportedCodecName,
} from "./constants.js";

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

export class ScrcpyMediaStreamParser {
  readonly #reader: AsyncByteReader;
  readonly #kind: "video" | "audio";
  readonly #maximumPacketSize: number;
  readonly #expectStreamMeta: boolean;
  readonly #fixedCodec: SupportedCodecName | undefined;
  #header: MediaStreamHeader | null = null;

  public constructor(reader: AsyncByteReader, options: MediaParserOptions) {
    this.#reader = reader;
    this.#kind = options.kind;
    this.#maximumPacketSize = options.maximumPacketSize ?? 64 * 1024 * 1024;
    this.#expectStreamMeta = options.expectStreamMeta ?? true;
    this.#fixedCodec = options.fixedCodec;
  }

  public async readHeader(): Promise<MediaStreamHeader> {
    if (this.#header) {
      return this.#header;
    }

    let codecId: number;
    let codec: SupportedCodecName;
    if (this.#expectStreamMeta) {
      codecId = await this.#reader.readU32();
      if (codecId === CodecId.Disabled) {
        throw new StreamDisabledError(false);
      }
      if (codecId === CodecId.ConfigurationError) {
        throw new StreamDisabledError(true);
      }
      const resolved = CODEC_NAMES[codecId];
      if (!resolved) {
        throw new UnsupportedCodecError(`unsupported scrcpy codec id 0x${codecId.toString(16).padStart(8, "0")}`);
      }
      codec = resolved;
    } else {
      if (!this.#fixedCodec) {
        throw new InvalidProtocolValueError("fixedCodec is required when stream metadata is disabled");
      }
      codec = this.#fixedCodec;
      codecId = codecNameToId(codec);
    }

    let session: VideoSessionMeta | undefined;
    if (this.#kind === "video" && this.#expectStreamMeta) {
      const raw = await this.#reader.readExactly(PACKET_HEADER_LENGTH);
      const flags = readU64be(raw, 0);
      if ((flags & PACKET_FLAG_SESSION) === 0n) {
        throw new InvalidProtocolValueError("expected a scrcpy video session header");
      }
      session = parseVideoSession(raw);
    }

    this.#header = session ? { codecId, codec, session } : { codecId, codec };
    return this.#header;
  }

  public async readPacket(): Promise<MediaPacket> {
    await this.readHeader();
    const rawHeader = await this.#reader.readExactly(PACKET_HEADER_LENGTH);
    const ptsAndFlags = readU64be(rawHeader, 0);
    if ((ptsAndFlags & PACKET_FLAG_SESSION) !== 0n) {
      if (this.#kind !== "video") {
        throw new InvalidProtocolValueError("unexpected session packet on audio stream");
      }
      const session = parseVideoSession(rawHeader);
      if (this.#header) {
        this.#header = { ...this.#header, session };
      }
      return {
        data: new Uint8Array(),
        pts: null,
        configuration: false,
        keyFrame: false,
        session,
      };
    }
    const packetLength = readU32be(rawHeader, 8);
    if (packetLength === 0) {
      throw new InvalidProtocolValueError("scrcpy media packet length is zero");
    }
    if (packetLength > this.#maximumPacketSize) {
      throw new InvalidProtocolValueError(
        `scrcpy media packet length ${packetLength} exceeds limit ${this.#maximumPacketSize}`,
      );
    }
    const configuration = (ptsAndFlags & PACKET_FLAG_CONFIG) !== 0n;
    const keyFrame = (ptsAndFlags & PACKET_FLAG_KEY_FRAME) !== 0n;
    return {
      data: await this.#reader.readExactly(packetLength),
      pts: configuration ? null : ptsAndFlags & PACKET_PTS_MASK,
      configuration,
      keyFrame,
    };
  }

  public async *packets(): AsyncGenerator<MediaPacket, never, void> {
    while (true) {
      yield await this.readPacket();
    }
  }
}

function codecNameToId(codec: SupportedCodecName): number {
  for (const [id, name] of Object.entries(CODEC_NAMES)) {
    if (name === codec) {
      return Number(id);
    }
  }
  throw new UnsupportedCodecError(`unknown codec name: ${codec}`);
}

function parseVideoSession(raw: Uint8Array): VideoSessionMeta {
  const session = {
    clientResized: (raw[3]! & 1) !== 0,
    width: readU32be(raw, 4),
    height: readU32be(raw, 8),
  };
  if (session.width === 0 || session.height === 0) {
    throw new InvalidProtocolValueError(`invalid scrcpy video size ${session.width}x${session.height}`);
  }
  return session;
}
