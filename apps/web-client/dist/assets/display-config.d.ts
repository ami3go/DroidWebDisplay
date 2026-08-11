import type { DisplayImePolicy, DisplayMode, VirtualDisplayConfigDto, VirtualDisplaySizeMode } from "./types.js";
export interface VirtualDisplayProfile extends VirtualDisplayConfigDto {
    readonly label: string;
    readonly videoCodec: "h264";
    readonly videoBitRate: number;
    readonly maxFps: number;
}
export declare const VIRTUAL_DISPLAY_PROFILES: Readonly<Record<string, VirtualDisplayProfile>>;
export interface DisplayFormValues {
    readonly displayMode: DisplayMode;
    readonly profileId: string;
    readonly sizeMode: VirtualDisplaySizeMode;
    readonly width: number;
    readonly height: number;
    readonly dpi: number;
    readonly startApp: string;
    readonly forceStopBeforeLaunch: boolean;
    readonly keepActive: boolean;
    readonly systemDecorations: boolean;
    readonly destroyContentOnClose: boolean;
    readonly imePolicy: DisplayImePolicy;
    readonly preserveAspectRatio: boolean;
    readonly videoBitRateMbps: number;
    readonly maxFps: number;
}
export declare function validateDisplayForm(values: DisplayFormValues): readonly string[];
export declare function buildSessionRequest(values: DisplayFormValues, serial: string): Record<string, unknown>;
export declare function alignedFlexSize(containerWidth: number, containerHeight: number, initialWidth: number, initialHeight: number, preserveAspectRatio: boolean): {
    width: number;
    height: number;
};
