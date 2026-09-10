export type AutoConnectDecision = "disabled" | "busy" | "waiting-for-device" | "paused-after-manual-disconnect" | "paused-after-failures" | "connect";
export interface AutoConnectState {
    readonly enabled: boolean;
    readonly connected: boolean;
    readonly connecting: boolean;
    readonly selectedReadySerial: string | null;
    readonly manualDisconnectSerial: string | null;
    readonly blockedSerial: string | null;
}
export type ReconnectAttemptSelection = "10" | "100" | "infinite";
/** Normalize current and legacy browser settings to a supported retry choice. */
export declare function normalizeReconnectAttemptSelection(value: unknown): ReconnectAttemptSelection;
/** Return null for an unlimited retry budget. */
export declare function reconnectAttemptLimit(value: unknown): number | null;
/** Progressive retry backoff, capped at one minute for responsive recovery. */
export declare function reconnectDelayMilliseconds(failureCount: number): number;
/**
 * Keep the USB auto-connect policy independent from browser and transport APIs.
 * A deliberate Disconnect must remain useful even while auto-reconnect is on,
 * and a repeatedly failing phone must not be hammered until it is replugged.
 */
export declare function decideAutoConnect(state: AutoConnectState): AutoConnectDecision;
