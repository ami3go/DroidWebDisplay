"use strict";
const workerScope = self;
let canvas = null;
let context = null;
let pendingFrame = null;
let scheduled = false;
let dropped = 0;
function closePending() {
    pendingFrame?.close();
    pendingFrame = null;
}
function postFatal(error) {
    closePending();
    scheduled = false;
    const message = error instanceof Error ? error.message : String(error);
    const transferable = canvas;
    context = null;
    canvas = null;
    if (transferable) {
        workerScope.postMessage({ type: "fatal", error: message, canvas: transferable }, [transferable]);
    }
    else {
        workerScope.postMessage({ type: "fatal", error: message });
    }
}
function schedulePresent() {
    if (scheduled)
        return;
    scheduled = true;
    setTimeout(presentLatest, 0);
}
function presentLatest() {
    scheduled = false;
    const frame = pendingFrame;
    pendingFrame = null;
    if (!frame || !canvas || !context) {
        frame?.close();
        return;
    }
    const startedAt = performance.now();
    try {
        context.drawImage(frame, 0, 0, canvas.width, canvas.height);
        workerScope.postMessage({
            type: "presented",
            timestamp: frame.timestamp,
            presentedAt: performance.timeOrigin + performance.now(),
            drawMilliseconds: Math.max(0, performance.now() - startedAt),
            dropped,
        });
        dropped = 0;
    }
    catch (error) {
        postFatal(error);
    }
    finally {
        frame.close();
    }
    if (pendingFrame && canvas && context)
        schedulePresent();
}
self.addEventListener("message", (event) => {
    const message = event.data;
    try {
        switch (message.type) {
            case "init":
                canvas = message.canvas;
                context = canvas.getContext("2d", { alpha: false, desynchronized: true });
                if (!context)
                    throw new Error("OffscreenCanvas 2D context is unavailable");
                workerScope.postMessage({ type: "ready" });
                break;
            case "resize":
                if (!canvas)
                    return;
                canvas.width = message.width;
                canvas.height = message.height;
                break;
            case "frame":
                if (!canvas || !context) {
                    message.frame.close();
                    return;
                }
                if (pendingFrame) {
                    pendingFrame.close();
                    dropped += 1;
                }
                pendingFrame = message.frame;
                schedulePresent();
                break;
            case "clear":
                closePending();
                dropped = 0;
                break;
        }
    }
    catch (error) {
        if (message.type === "frame")
            message.frame.close();
        postFatal(error);
    }
});
//# sourceMappingURL=video-render-worker.js.map