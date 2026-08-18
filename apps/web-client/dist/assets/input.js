const ControlMessageType = {
    InjectKeycode: 0,
    InjectText: 1,
    GetClipboard: 8,
    SetClipboard: 9,
};
export function mapClientPoint(clientX, clientY, rect, screen) {
    if (rect.width <= 0 || rect.height <= 0 || screen.width <= 0 || screen.height <= 0) {
        throw new Error("screen and display dimensions must be positive");
    }
    const normalizedX = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    const normalizedY = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height));
    return {
        x: Math.min(screen.width - 1, Math.round(normalizedX * (screen.width - 1))),
        y: Math.min(screen.height - 1, Math.round(normalizedY * (screen.height - 1))),
        screenWidth: screen.width,
        screenHeight: screen.height,
    };
}
const KEYCODES = {
    Backspace: 67,
    Enter: 66,
    Tab: 61,
    ArrowUp: 19,
    ArrowDown: 20,
    ArrowLeft: 21,
    ArrowRight: 22,
    Delete: 112,
    Insert: 124,
    PageUp: 92,
    PageDown: 93,
    Escape: 4,
};
export function clipboardShortcut(event) {
    if (event.altKey || (!event.ctrlKey && !event.metaKey))
        return null;
    const key = event.key.toLowerCase();
    // Ctrl/Cmd+V must stay a native browser paste so the document "paste"
    // handler can read ClipboardEvent.clipboardData without Async Clipboard permission.
    if (key === "v")
        return null;
    if (key === "c")
        return "copy";
    return null;
}
export function androidClipboardCopyMessage() {
    return { type: ControlMessageType.GetClipboard, copyKey: 1 };
}
export function keyboardMessages(event) {
    if (event.ctrlKey || event.metaKey || event.altKey)
        return [];
    if (event.key.length === 1) {
        return [{ type: ControlMessageType.InjectText, text: event.key }];
    }
    const keycode = KEYCODES[event.key];
    if (keycode === undefined)
        return [];
    const metaState = event.shiftKey ? 0x00000001 : 0;
    return [
        { type: ControlMessageType.InjectKeycode, action: 0, keycode, repeat: event.repeat ? 1 : 0, metaState },
        { type: ControlMessageType.InjectKeycode, action: 1, keycode, repeat: 0, metaState },
    ];
}
export function clipboardMessage(text, sequence, paste) {
    return { type: ControlMessageType.SetClipboard, sequence, paste, text };
}
export function androidKeyPress(keycode) {
    return [
        { type: ControlMessageType.InjectKeycode, action: 0, keycode, repeat: 0, metaState: 0 },
        { type: ControlMessageType.InjectKeycode, action: 1, keycode, repeat: 0, metaState: 0 },
    ];
}
export function textInjectionMessages(text, maximumUtf8Bytes = 300) {
    if (!Number.isInteger(maximumUtf8Bytes) || maximumUtf8Bytes <= 0) {
        throw new Error("maximumUtf8Bytes must be a positive integer");
    }
    const chunks = [];
    let current = "";
    let currentBytes = 0;
    const encoder = new TextEncoder();
    for (const symbol of text) {
        const bytes = encoder.encode(symbol).byteLength;
        if (bytes > maximumUtf8Bytes) {
            throw new Error("A text symbol exceeds the scrcpy injection limit");
        }
        if (current && currentBytes + bytes > maximumUtf8Bytes) {
            chunks.push(current);
            current = "";
            currentBytes = 0;
        }
        current += symbol;
        currentBytes += bytes;
    }
    if (current)
        chunks.push(current);
    return chunks.map((chunk) => ({ type: ControlMessageType.InjectText, text: chunk }));
}
//# sourceMappingURL=input.js.map