export type ScreenCopyShortcut = "smart" | "image" | null;

export function screenCopyShortcut(
  event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey">,
): ScreenCopyShortcut {
  if (event.altKey || (!event.ctrlKey && !event.metaKey) || event.key.toLowerCase() !== "c") return null;
  return event.shiftKey ? "image" : "smart";
}

export async function canvasPngBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  if (canvas.width <= 0 || canvas.height <= 0) throw new Error("Android display frame is not available yet");
  return await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("Could not encode the Android display frame as PNG"));
    }, "image/png");
  });
}

export async function writeCanvasPngToClipboard(canvas: HTMLCanvasElement): Promise<void> {
  if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
    throw new Error("This browser does not support writing images to the PC clipboard");
  }
  const blob = await canvasPngBlob(canvas);
  await navigator.clipboard.write([
    new ClipboardItem({ "image/png": blob }),
  ]);
}
