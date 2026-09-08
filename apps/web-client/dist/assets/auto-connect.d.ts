export type AutoConnectDecision = "disabled" | "busy" | "waiting-for-device" | "paused-after-manual-disconnect" | "paused-after-failures" | "connect";
export interface AutoConnectState {
    readonly enabled: boolean;
    readonly connected: boolean;
    readonly connecting: boolean;
    readonly selectedReadySerial: string | null;
    readonly manualDisconnectSerial: string | null;
    readonly blockedSerial: string | null;
}
/**
 * Keep the USB auto-connect policy independent from browser and transport APIs.
 * A deliberate Disconnect must remain useful even while auto-reconnect is on,
 * and a repeatedly failing phone must not be hammered until it is replugged.
 */
export declare function decideAutoConnect(state: AutoConnectState): AutoConnectDecision;
