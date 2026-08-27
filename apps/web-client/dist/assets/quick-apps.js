export const MAX_QUICK_APP_BUTTONS = 12;
const PACKAGE_PATTERN = /^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$/;
const RESERVED_KEYS = new Set(["__proto__", "constructor", "prototype"]);
export function normalizeQuickAppPackages(value) {
    if (!Array.isArray(value))
        return [];
    const packages = [];
    const seen = new Set();
    for (const candidate of value) {
        if (typeof candidate !== "string")
            continue;
        const packageName = candidate.trim();
        if (!PACKAGE_PATTERN.test(packageName) || seen.has(packageName))
            continue;
        packages.push(packageName);
        seen.add(packageName);
        if (packages.length === MAX_QUICK_APP_BUTTONS)
            break;
    }
    return packages;
}
export function normalizeQuickAppsByDevice(value) {
    if (!value || typeof value !== "object" || Array.isArray(value))
        return {};
    const normalized = {};
    for (const [serial, packages] of Object.entries(value)) {
        const cleanSerial = serial.trim();
        if (!cleanSerial || cleanSerial.length > 256 || RESERVED_KEYS.has(cleanSerial))
            continue;
        const cleanPackages = normalizeQuickAppPackages(packages);
        if (cleanPackages.length)
            normalized[cleanSerial] = cleanPackages;
    }
    return normalized;
}
export function nextQuickAppPackage(configured, catalog) {
    const assigned = new Set(configured);
    return catalog.find((app) => !assigned.has(app.packageName))?.packageName ?? null;
}
export function moveQuickApp(configured, index, offset) {
    const target = index + offset;
    if (index < 0 || index >= configured.length || target < 0 || target >= configured.length) {
        return [...configured];
    }
    const reordered = [...configured];
    const current = reordered[index];
    reordered[index] = reordered[target];
    reordered[target] = current;
    return reordered;
}
//# sourceMappingURL=quick-apps.js.map