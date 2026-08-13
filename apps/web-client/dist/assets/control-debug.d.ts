export interface ControlDebugEvent {
    readonly sequence: number;
    readonly timestamp: string;
    readonly monotonicMs: number;
    readonly category: string;
    readonly event: string;
    readonly details: Readonly<Record<string, unknown>>;
}
export declare function controlDebug(category: string, event: string, details?: Readonly<Record<string, unknown>>): void;
export declare function controlDebugEvents(): readonly ControlDebugEvent[];
export declare function clearControlDebugLog(): void;
export declare function controlDebugBundle(extra?: Readonly<Record<string, unknown>>): Record<string, unknown>;
export declare function downloadControlDebugBundle(extra?: Readonly<Record<string, unknown>>): void;
