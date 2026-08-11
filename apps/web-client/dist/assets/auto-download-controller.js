import { BridgeApi } from "./api.js";
export class AutoDownloadController {
    elements;
    #api = new BridgeApi();
    #timer = null;
    #snapshot = null;
    #lastNotificationTimestamp = Number(localStorage.getItem("gpt-bridge-auto-download-notification-ts") ?? "0");
    constructor(elements) {
        this.elements = elements;
        this.bindEvents();
    }
    async initialize() {
        const [roots, profiles, snapshot] = await Promise.all([
            this.#api.androidStorageRoots(this.elements.device.value || undefined),
            this.#api.destinationProfiles(),
            this.#api.autoDownload(),
        ]);
        this.elements.source.replaceChildren();
        for (const root of roots.roots) {
            const option = document.createElement("option");
            option.value = root.path;
            option.textContent = root.label;
            this.elements.source.append(option);
        }
        this.elements.destination.replaceChildren();
        for (const profile of profiles.profiles) {
            const option = document.createElement("option");
            option.value = profile.id;
            option.textContent = `${profile.id} · ${profile.path}`;
            this.elements.destination.append(option);
        }
        this.applySnapshot(snapshot, true);
        this.#timer = window.setInterval(() => void this.refresh(), 1000);
    }
    bindEvents() {
        this.elements.device.addEventListener("change", () => void this.runAction(() => this.refreshRoots()));
        this.elements.save.addEventListener("click", () => void this.runAction(() => this.save()));
        this.elements.scanNow.addEventListener("click", () => void this.runAction(async () => {
            const snapshot = await this.#api.scanAutoDownload();
            this.applySnapshot(snapshot);
        }));
        this.elements.reset.addEventListener("click", () => void this.runAction(async () => {
            const snapshot = await this.#api.resetAutoDownload();
            this.applySnapshot(snapshot);
        }));
        this.elements.notifications.addEventListener("change", () => void this.configureNotifications());
    }
    async refreshRoots() {
        const roots = await this.#api.androidStorageRoots(this.elements.device.value || undefined);
        const current = this.elements.source.value;
        this.elements.source.replaceChildren();
        for (const root of roots.roots) {
            const option = document.createElement("option");
            option.value = root.path;
            option.textContent = root.label;
            this.elements.source.append(option);
        }
        this.elements.source.value = [...this.elements.source.options].some((option) => option.value === current) ? current : roots.defaultPath;
    }
    async save() {
        const serial = this.elements.device.value || null;
        const snapshot = await this.#api.configureAutoDownload({
            enabled: this.elements.enabled.checked,
            pcToAndroidEnabled: this.elements.pcToAndroidEnabled.checked,
            serial,
            sourcePath: this.elements.source.value || "/sdcard/Download",
            destinationProfile: this.elements.destination.value || "default-downloads",
            duplicatePolicy: "rename",
            uploadDuplicatePolicy: this.elements.uploadDuplicatePolicy.value,
            scanIntervalSeconds: numberValue(this.elements.scanInterval, 2),
            stabilitySeconds: numberValue(this.elements.stabilitySeconds, 3),
            stabilityObservations: numberValue(this.elements.stabilityObservations, 3),
            includeExisting: this.elements.includeExisting.checked,
            includeExistingPc: this.elements.includeExistingPc.checked,
            deleteAfterVerified: this.elements.deleteAfterVerified.checked,
        });
        this.applySnapshot(snapshot);
    }
    async refresh() {
        try {
            this.applySnapshot(await this.#api.autoDownload());
        }
        catch (error) {
            this.elements.status.textContent = "Unavailable";
            this.elements.summary.textContent = errorMessage(error);
            this.elements.summary.classList.add("error-text");
        }
    }
    applySnapshot(snapshot, initialize = false) {
        this.#snapshot = snapshot;
        const config = snapshot.config;
        const runtime = snapshot.runtime;
        if (initialize) {
            this.elements.enabled.checked = config.enabled;
            this.elements.pcToAndroidEnabled.checked = config.pcToAndroidEnabled;
            setSelectValue(this.elements.source, config.sourcePath);
            setSelectValue(this.elements.destination, config.destinationProfile);
            setSelectValue(this.elements.uploadDuplicatePolicy, config.uploadDuplicatePolicy);
            this.elements.scanInterval.value = String(config.scanIntervalSeconds);
            this.elements.stabilitySeconds.value = String(config.stabilitySeconds);
            this.elements.stabilityObservations.value = String(config.stabilityObservations);
            this.elements.includeExisting.checked = config.includeExisting;
            this.elements.includeExistingPc.checked = config.includeExistingPc;
            this.elements.deleteAfterVerified.checked = config.deleteAfterVerified;
            this.elements.notifications.checked = localStorage.getItem("gpt-bridge-auto-download-notifications") === "true";
        }
        this.elements.status.textContent = runtime.state;
        this.elements.status.classList.toggle("error-text", runtime.state === "error");
        this.elements.summary.classList.toggle("error-text", Boolean(runtime.lastError));
        this.elements.summary.textContent = [
            `Android ${runtime.filesSeen} seen`,
            `PC ${runtime.pcFilesSeen} seen`,
            `${runtime.downloadsCompleted}/${runtime.downloadsQueued} downloaded`,
            `${runtime.uploadsCompleted}/${runtime.uploadsQueued} uploaded`,
            `${runtime.deletionsCompleted} Android source(s) deleted`,
            `${snapshot.processedFingerprints + snapshot.processedPcFingerprints} loop-prevention fingerprint(s)`,
            runtime.lastError ? `Error: ${runtime.lastError}` : null,
        ].filter(Boolean).join(" · ");
        this.renderEvents(snapshot);
        this.notifyNewEvents(snapshot);
    }
    renderEvents(snapshot) {
        this.elements.events.replaceChildren();
        const notifications = [...snapshot.runtime.notifications].reverse().slice(0, 25);
        if (!notifications.length) {
            const empty = document.createElement("p");
            empty.className = "empty-state";
            empty.textContent = "No automatic transfers yet.";
            this.elements.events.append(empty);
            return;
        }
        for (const item of notifications) {
            const row = document.createElement("div");
            row.className = `monitor-event event-${item.event}`;
            const title = document.createElement("strong");
            title.textContent = item.message;
            const detail = document.createElement("small");
            const path = item.destination ?? item.path ?? item.error ?? "";
            detail.textContent = `${new Date(item.timestamp * 1000).toLocaleString()}${path ? ` · ${path}` : ""}`;
            row.append(title, detail);
            this.elements.events.append(row);
        }
    }
    async configureNotifications() {
        localStorage.setItem("gpt-bridge-auto-download-notifications", String(this.elements.notifications.checked));
        if (!this.elements.notifications.checked || !("Notification" in globalThis))
            return;
        if (Notification.permission === "default")
            await Notification.requestPermission();
        if (Notification.permission !== "granted")
            this.elements.notifications.checked = false;
        localStorage.setItem("gpt-bridge-auto-download-notifications", String(this.elements.notifications.checked));
    }
    notifyNewEvents(snapshot) {
        const notifications = snapshot.runtime.notifications.filter((item) => item.timestamp > this.#lastNotificationTimestamp);
        if (!notifications.length)
            return;
        this.#lastNotificationTimestamp = Math.max(...notifications.map((item) => item.timestamp));
        localStorage.setItem("gpt-bridge-auto-download-notification-ts", String(this.#lastNotificationTimestamp));
        if (!this.elements.notifications.checked || !("Notification" in globalThis) || Notification.permission !== "granted")
            return;
        for (const item of notifications) {
            if (!["download-completed", "upload-completed", "monitor-error", "download-failed", "upload-failed"].includes(item.event))
                continue;
            new Notification("Gpt-Bridge", { body: item.message, tag: `gpt-bridge-${item.event}-${item.transferId ?? item.timestamp}` });
        }
    }
    async runAction(action) {
        try {
            await action();
        }
        catch (error) {
            this.elements.status.textContent = "Error";
            this.elements.status.classList.add("error-text");
            this.elements.summary.textContent = errorMessage(error);
            this.elements.summary.classList.add("error-text");
        }
    }
}
function numberValue(input, fallback) {
    const value = Number(input.value);
    return Number.isFinite(value) ? value : fallback;
}
function setSelectValue(select, value) {
    if ([...select.options].some((option) => option.value === value))
        select.value = value;
}
function errorMessage(error) {
    return error instanceof Error ? error.message : String(error);
}
//# sourceMappingURL=auto-download-controller.js.map