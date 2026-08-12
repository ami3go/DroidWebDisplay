type WorkerMessage = {
    readonly type: "init";
    readonly canvas: OffscreenCanvas;
} | {
    readonly type: "resize";
    readonly width: number;
    readonly height: number;
} | {
    readonly type: "frame";
    readonly frame: VideoFrame;
} | {
    readonly type: "clear";
};
declare let canvas: OffscreenCanvas | null;
declare let context: OffscreenCanvasRenderingContext2D | null;
declare let pendingFrame: VideoFrame | null;
declare let scheduled: boolean;
declare let dropped: number;
declare function closePending(): void;
declare function schedulePresent(): void;
declare function presentLatest(): void;
