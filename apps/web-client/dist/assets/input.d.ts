import type { ControlMessage, Position } from "@droid-web-display/scrcpy-protocol";
export interface RectLike {
    readonly left: number;
    readonly top: number;
    readonly width: number;
    readonly height: number;
}
export interface ScreenSize {
    readonly width: number;
    readonly height: number;
}
export declare function mapClientPoint(clientX: number, clientY: number, rect: RectLike, screen: ScreenSize): Position;
// "paste" is intentionally not a member: Ctrl/Cmd+V is never a shortcut here.
export type ClipboardShortcut = "copy" | null;
export declare function clipboardShortcut(event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey">): ClipboardShortcut;
export declare function androidClipboardCopyMessage(): ControlMessage;
export declare function keyboardMessages(event: Pick<KeyboardEvent, "key" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey" | "repeat">): ControlMessage[];
export declare function clipboardMessage(text: string, sequence: bigint, paste: boolean): ControlMessage;
export declare function androidKeyPress(keycode: number): ControlMessage[];
export declare function textInjectionMessages(text: string, maximumUtf8Bytes?: number): ControlMessage[];
