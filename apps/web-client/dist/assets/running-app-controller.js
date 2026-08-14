import { BridgeApi } from "./api.js";
const DROPDOWN_REFRESH_STALE_MS = 1500;
const STORAGE_REFRESH_MS = 30_000;
function errorMessage(error) {
    return error instanceof Error ? error.message : String(error);
}
function formatBytes(value) {
    const gib = value / (1024 ** 3);
    if (gib >= 1)
        return `${gib.toFixed(2)} GiB`;
    return `${(value / (1024 ** 2)).toFixed(0)} MiB`;
}
function metadataBytes(device, key) {
    const raw = device?.metadata?.[key];
    if (raw === undefined)
        return null;
    const value = Number(raw);
    return Number.isFinite(value) && value >= 0 ? value : null;
}
function formatStorage(freeBytes, totalBytes) {
    if (freeBytes === null)
        return "Unavailable";
    if (totalBytes === null || totalBytes <= 0)
        return `${formatBytes(freeBytes)} free`;
    return `${formatBytes(freeBytes)} free of ${formatBytes(totalBytes)}`;
}
function ensureDiagnosticValue(anchor, id, label) {
    const existing = document.getElementById(id);
    if (existing)
        return existing;
    const summary = anchor.closest(".device-diagnostic-summary");
    if (!summary)
        throw new Error("Missing diagnostics summary container");
    const row = document.createElement("div");
    const caption = document.createElement("span");
    const value = document.createElement("strong");
    caption.textContent = label;
    value.id = id;
    value.textContent = "—";
    row.append(caption, value);
    summary.append(row);
    return value;
}
export class RunningAppController {
    #api;
    #elements;
    #diagnosticInternalStorage;
    #diagnosticSdCard;
    #apps = [];
    #activeSession = null;
    #virtualSession = null;
    #deviceInfo = null;
    #deviceInfoAt = 0;
    #refreshing = false;
    #moving = false;
    #timer = null;
    #lastRefreshAt = 0;
    #dropdownActive = false;
    #refreshAfterDropdown = false;
    #refreshQueued = false;
    constructor(elements, api = new BridgeApi()) {
        this.#elements = elements;
        this.#api = api;
        this.#diagnosticInternalStorage = ensureDiagnosticValue(elements.diagnosticRam, "diagnostic-internal-storage", "Internal storage");
        this.#diagnosticSdCard = ensureDiagnosticValue(elements.diagnosticRam, "diagnostic-sd-card", "SD card");
        elements.icon.addEventListener("click", () => {
            this.#dropdownActive = false;
            this.#refreshAfterDropdown = false;
            void this.refresh();
        });
        elements.select.addEventListener("pointerdown", () => this.beginDropdownInteraction());
        elements.select.addEventListener("focus", () => this.beginDropdownInteraction());
        elements.select.addEventListener("change", () => void this.handleSelectionChange());
        elements.select.addEventListener("blur", () => void this.finishDropdownInteraction());
        elements.device.addEventListener("change", () => {
            this.#dropdownActive = false;
            this.#refreshAfterDropdown = false;
            this.#lastRefreshAt = 0;
            this.#deviceInfo = null;
            this.#deviceInfoAt = 0;
            if (this.#refreshing)
                this.#refreshQueued = true;
            else
                void this.refresh();
        });
    }
    async initialize() {
        await this.refresh();
        this.#timer = window.setInterval(() => {
            if (document.visibilityState === "visible")
                void this.refresh(true);
        }, 4000);
    }
    close() {
        if (this.#timer !== null)
            window.clearInterval(this.#timer);
        this.#timer = null;
    }
    async refresh(silent = false) {
        if (this.#refreshing) {
            this.#refreshQueued = true;
            return;
        }
        if (silent && this.#dropdownActive) {
            this.#refreshAfterDropdown = true;
            return;
        }
        const serial = this.#elements.device.value;
        if (!serial) {
            this.#apps = [];
            this.#activeSession = null;
            this.#virtualSession = null;
            this.#deviceInfo = null;
            this.#deviceInfoAt = 0;
            this.#lastRefreshAt = 0;
            this.render();
            this.renderDiagnostics(null, null);
            this.#elements.status.textContent = "Select an authorized Android device.";
            return;
        }
        this.#refreshing = true;
        if (!silent)
            this.#elements.status.textContent = "Reading running Android applications…";
        try {
            const [apps, sessions, deviceInfo] = await Promise.all([
                this.#api.runningApps(serial),
                this.#api.sessions(),
                this.loadDeviceInfo(serial, !silent),
            ]);
            if (this.#elements.device.value !== serial) {
                this.#refreshQueued = true;
                return;
            }
            this.#apps = apps.apps;
            this.#deviceInfo = deviceInfo;
            const runningSessions = sessions.sessions.filter((session) => session.serial === serial && session.state === "running");
            this.#virtualSession = runningSessions.find((session) => session.displayMode === "virtual"
                && typeof session.virtualDisplay.displayId === "number") ?? null;
            this.#activeSession = this.#virtualSession ?? runningSessions[0] ?? null;
            this.#lastRefreshAt = Date.now();
            this.render();
            this.renderDiagnostics(apps.freeMemoryBytes ?? null, deviceInfo);
            const displayId = this.#virtualSession?.virtualDisplay.displayId;
            this.#elements.status.textContent = displayId === null || displayId === undefined
                ? `${this.#apps.length} GUI task(s) found. Start a virtual display to move one.`
                : `${this.#apps.length} GUI task(s) found · target display ${displayId}.`;
            this.updateSelectionStatus();
        }
        catch (error) {
            this.#apps = [];
            this.#activeSession = null;
            this.#virtualSession = null;
            this.#deviceInfo = null;
            this.#deviceInfoAt = 0;
            this.render();
            this.renderDiagnostics(null, null);
            this.#elements.status.textContent = `Running-app query failed: ${errorMessage(error)}`;
        }
        finally {
            this.#refreshing = false;
            if (this.#refreshQueued) {
                this.#refreshQueued = false;
                void this.refresh(true);
            }
        }
    }
    async loadDeviceInfo(serial, force) {
        if (!force
            && this.#deviceInfo?.serial === serial
            && Date.now() - this.#deviceInfoAt < STORAGE_REFRESH_MS) {
            return this.#deviceInfo;
        }
        const response = await this.#api.devices();
        const device = response.devices.find((candidate) => candidate.serial === serial) ?? null;
        this.#deviceInfoAt = Date.now();
        return device;
    }
    beginDropdownInteraction() {
        this.#dropdownActive = true;
        if (Date.now() - this.#lastRefreshAt >= DROPDOWN_REFRESH_STALE_MS) {
            this.#refreshAfterDropdown = true;
        }
    }
    async finishDropdownInteraction() {
        this.#dropdownActive = false;
        if (!this.#refreshAfterDropdown)
            return;
        if (Date.now() - this.#lastRefreshAt < DROPDOWN_REFRESH_STALE_MS) {
            this.#refreshAfterDropdown = false;
            return;
        }
        if (this.#refreshing || this.#moving)
            return;
        this.#refreshAfterDropdown = false;
        await this.refresh(true);
    }
    async handleSelectionChange() {
        this.#dropdownActive = false;
        try {
            await this.moveSelected();
        }
        finally {
            await this.finishDropdownInteraction();
        }
    }
    render() {
        this.#elements.select.replaceChildren();
        this.#elements.count.textContent = String(this.#apps.length);
        this.#elements.icon.title = `Refresh running applications · ${this.#apps.length} GUI task(s)`;
        this.#elements.icon.setAttribute("aria-label", `Refresh running applications · ${this.#apps.length} GUI task(s)`);
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = this.#apps.length ? "Select application" : "No GUI apps";
        this.#elements.select.append(placeholder);
        for (const app of this.#apps) {
            const option = document.createElement("option");
            option.value = String(app.taskId);
            const display = app.displayId === null ? "display ?" : `display ${app.displayId}`;
            option.textContent = `${app.label} · ${display}`;
            option.dataset.component = app.componentName;
            this.#elements.select.append(option);
        }
        const current = this.currentVirtualApp();
        this.#elements.select.value = current ? String(current.taskId) : "";
        this.#elements.select.disabled = this.#apps.length === 0 || this.#moving;
        this.updateSelectionStatus();
    }
    currentVirtualApp() {
        const displayId = this.#virtualSession?.virtualDisplay.displayId ?? null;
        if (displayId === null)
            return null;
        return this.#apps.find((app) => app.displayId === displayId && app.resumed) ?? null;
    }
    selectedApp() {
        const taskId = Number(this.#elements.select.value);
        if (!Number.isInteger(taskId) || taskId <= 0)
            return null;
        return this.#apps.find((app) => app.taskId === taskId) ?? null;
    }
    updateSelectionStatus() {
        const app = this.selectedApp();
        const displayId = this.#virtualSession?.virtualDisplay.displayId ?? null;
        if (!app)
            return;
        if (displayId === null) {
            this.#elements.status.textContent = "Start a virtual display to move the selected application.";
            return;
        }
        this.#elements.status.textContent = app.displayId === displayId
            ? `${app.label} is active on virtual display ${displayId}.`
            : `${app.label} is ready to move to virtual display ${displayId}.`;
    }
    async moveSelected() {
        if (this.#moving)
            return;
        const app = this.selectedApp();
        const session = this.#virtualSession;
        const displayId = session?.virtualDisplay.displayId ?? null;
        if (!app || !session || displayId === null) {
            this.updateSelectionStatus();
            return;
        }
        this.#moving = true;
        this.#elements.select.disabled = true;
        this.#elements.status.textContent = `Moving ${app.label} to display ${displayId}…`;
        try {
            const result = await this.#api.moveRunningApp({
                sessionId: session.sessionId,
                taskId: app.taskId,
                componentName: app.componentName,
            });
            this.#elements.status.textContent = result.verified
                ? `${result.app.label} is on virtual display ${result.displayId}.`
                : `Launch request sent for ${result.app.label}; Android did not confirm relocation yet.`;
            await this.refresh(true);
        }
        catch (error) {
            const message = `Move failed: ${errorMessage(error)}`;
            await this.refresh(true);
            this.#elements.status.textContent = message;
        }
        finally {
            this.#moving = false;
            this.#elements.select.disabled = this.#apps.length === 0;
            this.updateSelectionStatus();
        }
    }
    renderDiagnostics(freeMemoryBytes, device) {
        const displayId = this.#virtualSession?.virtualDisplay.displayId
            ?? (this.#activeSession?.displayMode === "physical" ? 0 : null);
        this.#elements.diagnosticDisplay.textContent = displayId === null ? "—" : String(displayId);
        this.#elements.diagnosticRam.textContent = freeMemoryBytes === null ? "—" : formatBytes(freeMemoryBytes);
        if (device === null) {
            this.#diagnosticInternalStorage.textContent = "—";
            this.#diagnosticSdCard.textContent = "—";
            this.#diagnosticSdCard.removeAttribute("title");
            return;
        }
        this.#diagnosticInternalStorage.textContent = formatStorage(metadataBytes(device, "internalStorageFreeBytes"), metadataBytes(device, "internalStorageTotalBytes"));
        const sdPresent = device.metadata?.sdCardPresent;
        if (sdPresent === "false") {
            this.#diagnosticSdCard.textContent = "Not detected";
            this.#diagnosticSdCard.removeAttribute("title");
            return;
        }
        this.#diagnosticSdCard.textContent = formatStorage(metadataBytes(device, "sdCardFreeBytes"), metadataBytes(device, "sdCardTotalBytes"));
        const sdPath = device.metadata?.sdCardPath;
        if (sdPath)
            this.#diagnosticSdCard.title = sdPath;
        else
            this.#diagnosticSdCard.removeAttribute("title");
    }
}
//# sourceMappingURL=running-app-controller.js.map