export interface DeviceInfo {
    readonly name: string;
}
export interface Position {
    readonly x: number;
    readonly y: number;
    readonly screenWidth: number;
    readonly screenHeight: number;
}
export interface VideoSessionMeta {
    readonly width: number;
    readonly height: number;
    readonly clientResized: boolean;
}
export interface MediaPacket {
    readonly data: Uint8Array;
    readonly pts: bigint | null;
    readonly configuration: boolean;
    readonly keyFrame: boolean;
    /** Present when scrcpy starts a new capture session, for example after rotation. */
    readonly session?: VideoSessionMeta;
}
