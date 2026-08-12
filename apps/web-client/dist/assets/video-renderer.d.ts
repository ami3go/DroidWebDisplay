import { type ScrcpyV41Session } from "@droid-web-display/scrcpy-protocol";
export interface VideoStatistics {
    readonly framesDecoded: number;
    readonly framesPresented: number;
    readonly framesDropped: number;
    readonly width: number;
    readonly height: number;
    readonly decoderQueue: number;
    readonly lastPts: number;
    readonly sessionChanges: number;
    readonly fps: number;
    readonly decodeLatencyMs: number;
    readonly presentationLatencyMs: number;
    readonly browserPipelineMs: number;
    readonly decoderRecoveries: number;
    readonly rendererBackend: "offscreen-worker" | "canvas2d";
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
    private initializeRenderingBackend;
    private processPacket;
    private applySession;
    private configure;
    private createConfiguredDecoder;
    private recoverDecoderBacklog;
    private closeDecoder;
    private queueDecodedFrame;
    private presentLatestFrame;
    private onWorkerMessage;
    private recordPresentation;
    private clearPendingFrame;
    private resizeCanvas;
    private resolveResizeWaiters;
    private emitStatistics;
    private trimTimingMaps;
}
