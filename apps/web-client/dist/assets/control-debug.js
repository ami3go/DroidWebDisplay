const MAX_CONTROL_DEBUG_EVENTS = 1500;
const events = [];
let sequence = 0;
function monotonicNow() {
    return globalThis.performance?.now?.() ?? Date.now();
}
function safeValue(key, value) {
    // Never persist user text, clipboard data, auth material or opaque payloads in
    // a diagnostic bundle. Control debugging needs lifecycle/transport metadata only.
    if (/(text|clipboard|pin|password|token|cookie|authorization|payload|content)/i.test(key))
        return "<redacted>";
    if (typeof value === "bigint")
        return value.toString();
    if (value instanceof Error)
        return { name: value.name, message: value.message };
    if (Array.isArray(value))
        return value.slice(0, 32).map((item, index) => safeValue(String(index), item));
    if (value && typeof value === "object") {
        const output = {};
        for (const [childKey, childValue] of Object.entries(value).slice(0, 64)) {
            output[childKey] = safeValue(childKey, childValue);
        }
        return output;
    }
    if (typeof value === "string")
        return value.slice(0, 240);
    return value;
}
function safeDetails(details) {
    return safeValue("details", details);
}
export function controlDebug(category, event, details = {}) {
    const entry = {
        sequence: ++sequence,
        timestamp: new Date().toISOString(),
        monotonicMs: monotonicNow(),
        category,
        event,
        details: safeDetails(details),
    };
    events.push(entry);
    if (events.length > MAX_CONTROL_DEBUG_EVENTS)
        events.splice(0, events.length - MAX_CONTROL_DEBUG_EVENTS);
    globalThis.__dwdControlDebugEvents = events;
    globalThis.dispatchEvent(new CustomEvent("droidwebdisplay-control-debug", { detail: entry }));
}
export function controlDebugEvents() {
    return [...events];
}
export function clearControlDebugLog() {
    events.length = 0;
    sequence = 0;
    globalThis.__dwdControlDebugEvents = events;
    globalThis.dispatchEvent(new CustomEvent("droidwebdisplay-control-debug-cleared"));
}
export function controlDebugBundle(extra = {}) {
    const root = globalThis;
    return {
        schemaVersion: 1,
        generatedAt: new Date().toISOString(),
        browser: {
            userAgent: navigator.userAgent,
            language: navigator.language,
            visibilityState: document.visibilityState,
            documentHasFocus: document.hasFocus(),
            activeElement: document.activeElement?.tagName ?? null,
            origin: location.origin,
        },
        latencyMetrics: safeValue("latencyMetrics", { ...(root.__dwdLatencyMetrics ?? {}) }),
        extra: safeDetails(extra),
        events: controlDebugEvents(),
    };
}
export function downloadControlDebugBundle(extra = {}) {
    const payload = JSON.stringify(controlDebugBundle(extra), null, 2);
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    anchor.href = url;
    anchor.download = `droidwebdisplay-control-debug-${stamp}.json`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
//# sourceMappingURL=control-debug.js.map