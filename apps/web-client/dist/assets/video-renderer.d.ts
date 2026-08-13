import { type ScrcpyV41Session } from "@droid-web-display/scrcpy-protocol";
export type DecoderBacklogAction = "decode" | "recover-at-keyframe";
export declare function decoderBacklogAction(queueSize: number, packetIsKeyFrame: boolean): DecoderBacklogAction;
export interface VideoStatistics {
    readonly framesDecoded: number;
    readonly framesDropped: number;
    readonly width: number;
    readonly height: number;
    readonly decoderQueue: number;
    readonly lastPts: number;
    readonly sessionChanges: number;
}
export type StatisticsListener = (statistics: VideoStatistics) => void;
export declare class WebCodecsVideoRenderer {
    #private;
    private readonly canvas;
    private readonly onStatistics;
    constructor(canvas: HTMLCanvasElement, onStatistics?: StatisticsListener);
    get screenSize(): {
        width: number;
        height: number;
    };
    run(session: ScrcpyV41Session): Promise<void>;
    stop(): void;
    waitForScreenSizeChange(previous: {
        width: number;
        height: number;
    }, timeoutMs?: number): Promise<{
        width: number;
        height: number;
    }>;
    private processPacket;
    private applySession;
    private configure;
    private createConfiguredDecoder;
    private recoverDecoderAtKeyFrame;
    private closeDecoder;
    private drawFrame;
    private resizeCanvas;
    private resolveResizeWaiters;
    private emitStatistics;
}
