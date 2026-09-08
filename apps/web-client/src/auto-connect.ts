export type AutoConnectDecision =
  | "disabled"
  | "busy"
  | "waiting-for-device"
  | "paused-after-manual-disconnect"
  | "paused-after-failures"
  | "connect";

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
export function decideAutoConnect(state: AutoConnectState): AutoConnectDecision {
  if (!state.enabled) return "disabled";
  if (state.connected || state.connecting) return "busy";
  if (!state.selectedReadySerial) return "waiting-for-device";
  if (state.selectedReadySerial === state.manualDisconnectSerial) return "paused-after-manual-disconnect";
  if (state.selectedReadySerial === state.blockedSerial) return "paused-after-failures";
  return "connect";
}
