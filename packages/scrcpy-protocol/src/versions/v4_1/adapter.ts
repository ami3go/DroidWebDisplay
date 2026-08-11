import { AsyncByteReader } from "../../common/async-byte-reader.js";
import { InvalidProtocolValueError, StreamDisabledError, VersionMismatchError } from "../../common/errors.js";
import type { BridgeTransport, CompatibilityResult, ServerInfo, SessionOptions } from "../../common/transport.js";
import type { DeviceInfo, MediaPacket } from "../../common/types.js";
import { ADAPTER_ID, SCRCPY_VERSION } from "./constants.js";
import { type ControlMessage, serializeControlMessage } from "./control.js";
import { DeviceMessageParser, type DeviceMessage } from "./device.js";
import { readDeviceInfo, readDummyByte } from "./handshake.js";
import { ScrcpyMediaStreamParser, type MediaStreamHeader } from "./media.js";

export interface ScrcpyV41Session {
  readonly device: DeviceInfo | null;
  readonly videoHeader: MediaStreamHeader | null;
  readonly audioHeader: MediaStreamHeader | null;
  readVideoPacket(): Promise<MediaPacket>;
  readAudioPacket(): Promise<MediaPacket>;
  readDeviceMessage(): Promise<DeviceMessage>;
  sendControl(message: ControlMessage): Promise<void>;
  close(): Promise<void>;
}

export class ScrcpyV41Adapter {
  public readonly adapterId = ADAPTER_ID;
  public readonly scrcpyVersion = SCRCPY_VERSION;

  public validateServer(serverInfo: ServerInfo): CompatibilityResult {
    if (serverInfo.scrcpyVersion !== SCRCPY_VERSION) {
      return { compatible: false, reason: `expected scrcpy ${SCRCPY_VERSION}, got ${serverInfo.scrcpyVersion}` };
    }
    if (serverInfo.adapterId !== ADAPTER_ID) {
      return { compatible: false, reason: `expected adapter ${ADAPTER_ID}, got ${serverInfo.adapterId}` };
    }
    return { compatible: true };
  }

  public async connect(transport: BridgeTransport, options: SessionOptions): Promise<ScrcpyV41Session> {
    if (!options.video && !options.audio && !options.control) {
      throw new InvalidProtocolValueError("at least one scrcpy channel must be enabled");
    }

    const videoStream = options.video ? await transport.openVideoChannel() : null;
    const audioStream = options.audio ? await transport.openAudioChannel() : null;
    const controlPair = options.control ? await transport.openControlChannel() : null;

    const firstReader = videoStream
      ? new AsyncByteReader(videoStream, { label: "scrcpy video" })
      : audioStream
        ? new AsyncByteReader(audioStream, { label: "scrcpy audio" })
        : controlPair
          ? new AsyncByteReader(controlPair.readable, { label: "scrcpy control" })
          : null;
    if (!firstReader) {
      throw new VersionMismatchError("unable to select first scrcpy channel");
    }

    if (options.expectDummyByte ?? true) {
      await readDummyByte(firstReader);
    }
    const device = (options.expectDeviceMeta ?? true) ? await readDeviceInfo(firstReader) : null;

    const videoReader = videoStream ? firstReader : null;
    const audioReader = audioStream
      ? (videoStream ? new AsyncByteReader(audioStream, { label: "scrcpy audio" }) : firstReader)
      : null;
    const controlReader = controlPair
      ? (videoStream || audioStream ? new AsyncByteReader(controlPair.readable, { label: "scrcpy control" }) : firstReader)
      : null;

    const videoParser = videoReader
      ? new ScrcpyMediaStreamParser(videoReader, { kind: "video", expectStreamMeta: options.expectStreamMeta ?? true })
      : null;
    let audioParser = audioReader
      ? new ScrcpyMediaStreamParser(audioReader, { kind: "audio", expectStreamMeta: options.expectStreamMeta ?? true })
      : null;
    const deviceParser = controlReader ? new DeviceMessageParser(controlReader) : null;
    const controlWriter = controlPair?.writable.getWriter() ?? null;

    const videoHeader = videoParser ? await videoParser.readHeader() : null;
    let audioHeader: MediaStreamHeader | null = null;
    if (audioParser) {
      try {
        audioHeader = await audioParser.readHeader();
      } catch (error) {
        if (error instanceof StreamDisabledError) {
          // Audio is optional. A capture or encoder configuration failure must
          // not terminate video/control; the UI reports audio as unavailable.
          audioParser = null;
        } else {
          throw error;
        }
      }
    }

    return {
      device,
      videoHeader,
      audioHeader,
      readVideoPacket: async () => {
        if (!videoParser) throw new VersionMismatchError("video channel is disabled");
        return videoParser.readPacket();
      },
      readAudioPacket: async () => {
        if (!audioParser) throw new VersionMismatchError("audio channel is disabled");
        return audioParser.readPacket();
      },
      readDeviceMessage: async () => {
        if (!deviceParser) throw new VersionMismatchError("control channel is disabled");
        return deviceParser.read();
      },
      sendControl: async (message) => {
        if (!controlWriter) throw new VersionMismatchError("control channel is disabled");
        await controlWriter.write(serializeControlMessage(message));
      },
      close: async () => {
        try {
          await controlWriter?.close();
        } finally {
          await transport.close();
        }
      },
    };
  }
}
