import type { BridgeTransport, CompatibilityResult, ServerInfo, SessionOptions } from "../../common/transport.js";
import type { DeviceInfo, MediaPacket } from "../../common/types.js";
import { type ControlMessage } from "./control.js";
import { type DeviceMessage } from "./device.js";
import { type MediaStreamHeader } from "./media.js";
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
export declare class ScrcpyV41Adapter {
    readonly adapterId = "scrcpy-4.1";
    readonly scrcpyVersion = "4.1";
    validateServer(serverInfo: ServerInfo): CompatibilityResult;
    connect(transport: BridgeTransport, options: SessionOptions): Promise<ScrcpyV41Session>;
}
