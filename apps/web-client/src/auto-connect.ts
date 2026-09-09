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

export type ReconnectAttemptSelection = "10" | "100" | "infinite";

const RECONNECT_DELAYS_MS = [1_000, 2_000, 5_000, 10_000, 30_000, 60_000] as const;

/** Normalize current and legacy browser settings to a supported retry choice. */
export function normalizeReconnectAttemptSelection(value: unknown): ReconnectAttemptSelection {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "infinite" || normalized === "∞") return "infinite";
  if (normalized === "100") return "100";
  return "10";
}

/** Return null for an unlimited retry budget. */
export function reconnectAttemptLimit(value: unknown): number | null {
  const selection = normalizeReconnectAttemptSelection(value);
  return selection === "infinite" ? null : Number(selection);
}

/** Progressive retry backoff, capped at one minute for responsive recovery. */
export function reconnectDelayMilliseconds(failureCount: number): number {
  const safeCount = Number.isFinite(failureCount) ? Math.max(0, Math.floor(failureCount)) : 0;
  return RECONNECT_DELAYS_MS[Math.min(safeCount, RECONNECT_DELAYS_MS.length - 1)]!;
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
