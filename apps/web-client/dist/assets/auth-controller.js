import { BridgeApi, BridgeApiError } from "./api.js";
function formatTimestamp(value) {
    if (value === null)
        return "Until revoked";
    return new Date(value * 1000).toLocaleString();
}
function customSeconds(value, unit) {
    const factor = unit === "minutes" ? 60 : (unit === "hours" ? 3600 : 86400);
    return Math.round(value * factor);
}
export class AuthController {
    elements;
    #api;
    #status = null;
    constructor(elements, api = new BridgeApi()) {
        this.elements = elements;
        this.#api = api;
        elements.duration.addEventListener("change", () => this.#syncCustomVisibility());
        elements.form.addEventListener("submit", (event) => { event.preventDefault(); void this.#submit(); });
        elements.refreshSessions.addEventListener("click", () => { void this.refreshSessions(); });
        elements.logout.addEventListener("click", () => { void this.logout(); });
        elements.changePin.addEventListener("click", () => { void this.changePin(); });
        elements.revokeAll.addEventListener("click", () => { void this.revokeAll(); });
        globalThis.addEventListener("gpt-bridge-auth-required", () => {
            this.elements.gate.hidden = false;
            this.elements.securityStatus.textContent = "Session expired or revoked. Authenticate again.";
        });
    }
    async ensureAuthenticated() {
        const status = await this.#api.authStatus();
        this.#status = status;
        if (status.authenticated) {
            this.#showAuthenticated(status);
            return status;
        }
        this.#renderGate(status.configured);
        return new Promise((resolve) => {
            const listener = (event) => {
                const value = event.detail;
                globalThis.removeEventListener("gpt-bridge-authenticated", listener);
                resolve(value);
            };
            globalThis.addEventListener("gpt-bridge-authenticated", listener);
        });
    }
    async refreshSessions() {
        try {
            const response = await this.#api.authSessions();
            this.elements.sessionList.replaceChildren(...response.sessions.map((session) => this.#sessionRow(session)));
            if (!response.sessions.length)
                this.elements.sessionList.textContent = "No trusted browser sessions.";
            this.elements.securityStatus.textContent = "Trusted sessions refreshed.";
        }
        catch (error) {
            this.#showSecurityError(error);
        }
    }
    async logout() {
        try {
            await this.#api.authLogout();
            globalThis.location.reload();
        }
        catch (error) {
            this.#showSecurityError(error);
        }
    }
    async changePin() {
        const currentPin = this.elements.currentPin.value;
        const newPin = this.elements.newPin.value;
        const confirmPin = this.elements.confirmNewPin.value;
        try {
            await this.#api.changeAuthPin(currentPin, newPin, confirmPin);
            this.elements.securityStatus.textContent = "PIN changed. All trusted sessions were revoked.";
            globalThis.location.reload();
        }
        catch (error) {
            this.#showSecurityError(error);
        }
    }
    async revokeAll() {
        try {
            const result = await this.#api.revokeAllAuthSessions(this.elements.revokeAllPin.value);
            this.elements.securityStatus.textContent = `Revoked ${result.revoked} trusted session(s).`;
            globalThis.location.reload();
        }
        catch (error) {
            this.#showSecurityError(error);
        }
    }
    #renderGate(configured) {
        this.elements.gate.hidden = false;
        this.elements.title.textContent = configured ? "Unlock Gpt-Bridge" : "Create bridge PIN";
        this.elements.explanation.textContent = configured
            ? "Enter the PIN configured on this PC. Android does not remember or authorize this browser."
            : "Create a PIN for this PC-local bridge. It protects the local web service; it is not stored on the Android phone.";
        this.elements.confirmRow.hidden = configured;
        this.elements.submit.textContent = configured ? "Unlock" : "Create PIN and unlock";
        this.elements.error.textContent = "";
        this.elements.pin.value = "";
        this.elements.confirmPin.value = "";
        this.#syncCustomVisibility();
        queueMicrotask(() => this.elements.pin.focus());
    }
    async #submit() {
        this.elements.submit.disabled = true;
        this.elements.error.textContent = "";
        const configured = this.#status?.configured ?? false;
        const duration = this.elements.duration.value;
        const custom = duration === "custom"
            ? customSeconds(Number(this.elements.customValue.value), this.elements.customUnit.value)
            : undefined;
        try {
            const optional = {
                ...(custom === undefined ? {} : { customSeconds: custom }),
                ...(this.elements.label.value ? { label: this.elements.label.value } : {}),
            };
            const status = configured
                ? await this.#api.authLogin({
                    pin: this.elements.pin.value,
                    duration,
                    ...optional,
                })
                : await this.#api.authSetup({
                    pin: this.elements.pin.value,
                    confirmPin: this.elements.confirmPin.value,
                    duration,
                    ...optional,
                });
            this.#status = status;
            this.#showAuthenticated(status);
            globalThis.dispatchEvent(new CustomEvent("gpt-bridge-authenticated", { detail: status }));
        }
        catch (error) {
            this.elements.error.textContent = error instanceof BridgeApiError ? error.message : String(error);
        }
        finally {
            this.elements.submit.disabled = false;
        }
    }
    #showAuthenticated(status) {
        this.elements.gate.hidden = true;
        this.elements.securityCard.hidden = false;
        const session = status.currentSession;
        this.elements.sessionSummary.textContent = session
            ? `${session.label} · trusted until ${formatTimestamp(session.expiresAt)}`
            : "Authenticated PC-local session";
        void this.refreshSessions();
    }
    #sessionRow(session) {
        const row = document.createElement("div");
        row.className = `trusted-session-row${session.revokedAt ? " revoked" : ""}`;
        const info = document.createElement("div");
        const title = document.createElement("strong");
        title.textContent = `${session.label}${session.current ? " · Current" : ""}`;
        const details = document.createElement("small");
        details.textContent = session.revokedAt
            ? `Revoked: ${session.revocationReason ?? "yes"}`
            : `Expires: ${formatTimestamp(session.expiresAt)}`;
        info.append(title, details);
        const button = document.createElement("button");
        button.type = "button";
        button.className = "secondary compact";
        button.textContent = "Revoke";
        button.disabled = session.revokedAt !== null;
        button.addEventListener("click", () => {
            void this.#api.revokeAuthSession(session.sessionId).then((result) => {
                if (result.currentSessionRevoked)
                    globalThis.location.reload();
                else
                    void this.refreshSessions();
            }).catch((error) => this.#showSecurityError(error));
        });
        row.append(info, button);
        return row;
    }
    #syncCustomVisibility() {
        this.elements.customRow.hidden = this.elements.duration.value !== "custom";
    }
    #showSecurityError(error) {
        this.elements.securityStatus.textContent = error instanceof BridgeApiError ? error.message : String(error);
    }
}
//# sourceMappingURL=auth-controller.js.map