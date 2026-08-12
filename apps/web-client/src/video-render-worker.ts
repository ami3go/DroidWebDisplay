type WorkerMessage =
  | { readonly type: "init"; readonly canvas: OffscreenCanvas }
  | { readonly type: "resize"; readonly width: number; readonly height: number }
  | { readonly type: "frame"; readonly frame: VideoFrame }
  | { readonly type: "clear" };

let canvas: OffscreenCanvas | null = null;
let context: OffscreenCanvasRenderingContext2D | null = null;
let pendingFrame: VideoFrame | null = null;
let scheduled = false;
let dropped = 0;

function closePending(): void {
  pendingFrame?.close();
  pendingFrame = null;
}

function schedulePresent(): void {
  if (scheduled) return;
  scheduled = true;
  setTimeout(presentLatest, 0);
}

function presentLatest(): void {
  scheduled = false;
  const frame = pendingFrame;
  pendingFrame = null;
  if (!frame || !canvas || !context) return;
  const startedAt = performance.now();
  try {
    context.drawImage(frame, 0, 0, canvas.width, canvas.height);
    postMessage({
      type: "presented",
      timestamp: frame.timestamp,
      presentedAt: performance.now(),
      drawMilliseconds: Math.max(0, performance.now() - startedAt),
      dropped,
    });
    dropped = 0;
  } finally {
    frame.close();
  }
  if (pendingFrame) schedulePresent();
}

self.addEventListener("message", (event: MessageEvent<WorkerMessage>) => {
  const message = event.data;
  switch (message.type) {
    case "init":
      canvas = message.canvas;
      context = canvas.getContext("2d", { alpha: false, desynchronized: true });
      if (!context) throw new Error("OffscreenCanvas 2D context is unavailable");
      postMessage({ type: "ready" });
      break;
    case "resize":
      if (!canvas) return;
      canvas.width = message.width;
      canvas.height = message.height;
      break;
    case "frame":
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
});
