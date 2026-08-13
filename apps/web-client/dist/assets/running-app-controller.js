import { BridgeApi } from "./api.js";
function errorMessage(error) {
    return error instanceof Error ? error.message : String(error);
}
export class RunningAppController {
    #api;
    #elements;
    #apps = [];
    #virtualSession = null;
    #refreshing = false;
    #timer = null;
    #activeSessionId = null;
    constructor(elements, api = new BridgeApi()) {
        this.#elements = elements;
        this.#api = api;
        elements.refresh.addEventListener("click", () => void this.refresh());
        elements.move.addEventListener("click", () => void this.moveSelected());
        elements.select.addEventListener("change", () => this.updateControls());
        elements.device.addEventListener("change", () => void this.refresh());
        globalThis.addEventListener("droidwebdisplay-active-session", (event) => {
            const detail = event.detail;
            this.#activeSessionId = detail?.sessionId ?? null;
            void this.refresh(true);
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
        if (this.#refreshing)
            return;
        const serial = this.#elements.device.value;
        if (!serial) {
            this.#apps = [];
            this.#virtualSession = null;
            this.render();
            this.#elements.status.textContent = "Select an authorized Android device.";
            return;
        }
        this.#refreshing = true;
        if (!silent)
            this.#elements.status.textContent = "Reading running Android applications…";
        try {
            const [apps, sessions] = await Promise.all([this.#api.runningApps(serial), this.#api.deviceSessions(serial)]);
            this.#apps = apps.apps;
            const virtualSessions = sessions.sessions.filter((session) => session.state === "running"
                && session.displayMode === "virtual"
                && typeof session.virtualDisplay.displayId === "number");
            this.#virtualSession = virtualSessions.find((session) => session.sessionId === this.#activeSessionId)
                ?? (this.#activeSessionId === null ? virtualSessions[0] ?? null : null);
            this.render();
            const displayId = this.#virtualSession?.virtualDisplay.displayId;
            this.#elements.status.textContent = displayId === null || displayId === undefined
                ? `${this.#apps.length} GUI task(s) found. Start a virtual display to move one.`
                : `${this.#apps.length} GUI task(s) found · target display ${displayId}.`;
        }
        catch (error) {
            this.#apps = [];
            this.#virtualSession = null;
            this.render();
            this.#elements.status.textContent = `Running-app query failed: ${errorMessage(error)}`;
        }
        finally {
            this.#refreshing = false;
        }
    }
    render() {
        const previous = this.#elements.select.value;
        this.#elements.select.replaceChildren();
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = this.#apps.length ? "Select a running application" : "No GUI applications detected";
        this.#elements.select.append(placeholder);
        for (const app of this.#apps) {
            const option = document.createElement("option");
            option.value = String(app.taskId);
            const state = app.resumed ? "active" : app.visible ? "visible" : "background";
            const display = app.displayId === null ? "display ?" : `display ${app.displayId}`;
            option.textContent = `${app.label} · ${state} · ${display} · task ${app.taskId}`;
            option.dataset.component = app.componentName;
            this.#elements.select.append(option);
        }
        if ([...this.#elements.select.options].some((option) => option.value === previous)) {
            this.#elements.select.value = previous;
        }
        this.updateControls();
    }
    selectedApp() {
        const taskId = Number(this.#elements.select.value);
        if (!Number.isInteger(taskId) || taskId <= 0)
            return null;
        return this.#apps.find((app) => app.taskId === taskId) ?? null;
    }
    updateControls() {
        const app = this.selectedApp();
        const displayId = this.#virtualSession?.virtualDisplay.displayId ?? null;
        const alreadyThere = app !== null && displayId !== null && app.displayId === displayId;
        this.#elements.move.disabled = app === null || displayId === null || alreadyThere;
        this.#elements.move.textContent = alreadyThere
            ? "Already on virtual display"
            : displayId === null ? "Move to virtual display" : `Move to display ${displayId}`;
    }
    async moveSelected() {
        const app = this.selectedApp();
        const session = this.#virtualSession;
        if (!app || !session || session.virtualDisplay.displayId === null)
            return;
        this.#elements.move.disabled = true;
        this.#elements.status.textContent = `Moving ${app.label} to display ${session.virtualDisplay.displayId}…`;
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
            this.#elements.status.textContent = `Move failed: ${errorMessage(error)}`;
            this.updateControls();
        }
    }
}
//# sourceMappingURL=running-app-controller.js.map