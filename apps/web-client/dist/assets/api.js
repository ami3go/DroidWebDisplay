const windowFetch = (input, init) => globalThis.fetch(input, init);
let sharedCsrfToken = null;
export function setSharedCsrfToken(value) {
    sharedCsrfToken = value;
}
export class BridgeApiError extends Error {
    status;
    details;
    constructor(message, status, details) {
        super(message);
        this.status = status;
        this.details = details;
        this.name = "BridgeApiError";
    }
}
export class BridgeApi {
    baseUrl;
    fetchImpl;
    constructor(baseUrl = "", fetchImpl = windowFetch) {
        this.baseUrl = baseUrl;
        this.fetchImpl = fetchImpl;
    }
    async authStatus() {
        const value = await this.request("/api/v1/auth/status", undefined, true);
        setSharedCsrfToken(value.csrfToken);
        return value;
    }
    async authSetup(request) {
        const value = await this.request("/api/v1/auth/setup", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(request),
        }, true);
        setSharedCsrfToken(value.csrfToken);
        return value;
    }
    async authLogin(request) {
        const value = await this.request("/api/v1/auth/login", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(request),
        }, true);
        setSharedCsrfToken(value.csrfToken);
        return value;
    }
    async authLogout() {
        const value = await this.request("/api/v1/auth/logout", { method: "POST" });
        setSharedCsrfToken(null);
        return value;
    }
    async authSessions() {
        return this.request("/api/v1/auth/sessions");
    }
    async revokeAuthSession(sessionId) {
        return this.request(`/api/v1/auth/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
    }
    async revokeAllAuthSessions(pin) {
        const value = await this.request("/api/v1/auth/sessions/revoke-all", {
            method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ pin }),
        });
        setSharedCsrfToken(null);
        return value;
    }
    async changeAuthPin(currentPin, newPin, confirmPin) {
        const value = await this.request("/api/v1/auth/change-pin", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ currentPin, newPin, confirmPin }),
        });
        setSharedCsrfToken(null);
        return value;
    }
    async authAudit() {
        return this.request("/api/v1/auth/audit");
    }
    async devices() {
        return this.request("/api/v1/devices");
    }
    async browserSupport() {
        return this.request("/api/v1/browser-support");
    }
    async virtualDisplayCapabilities(serial, startApp = "com.openai.chatgpt") {
        const query = new URLSearchParams({ startApp });
        return this.request(`/api/v1/devices/${encodeURIComponent(serial)}/virtual-display-capabilities?${query.toString()}`);
    }
    async launchableApps(serial) {
        return this.request(`/api/v1/devices/${encodeURIComponent(serial)}/apps`);
    }
    async runningApps(serial) {
        return this.request(`/api/v1/devices/${encodeURIComponent(serial)}/running-apps`);
    }
    async moveRunningApp(request) {
        return this.request(`/api/v1/sessions/${encodeURIComponent(request.sessionId)}/virtual-display/move-running-app`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ taskId: request.taskId, componentName: request.componentName }),
        });
    }
    async virtualDisplayProfiles() {
        return this.request("/api/v1/virtual-display-profiles");
    }
    async sessions() {
        return this.request("/api/v1/sessions");
    }
    async startSession(request) {
        return this.request("/api/v1/sessions", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({
                video: true,
                audio: false,
                control: true,
                audioCodec: "opus",
                audioBitRate: 128_000,
                videoCodec: "h264",
                maxSize: 1920,
                videoBitRate: 8_000_000,
                maxFps: 30,
                displayMode: "physical",
                ...request,
            }),
        });
    }
    async androidStorage(serial, path) {
        const query = new URLSearchParams({ serial, path });
        return this.request(`/api/v1/storage/android?${query.toString()}`);
    }
    async deleteAndroidStorage(serial, path) {
        const query = new URLSearchParams({ serial, path });
        return this.request(`/api/v1/storage/android?${query.toString()}`, { method: "DELETE" });
    }
    async androidStorageRoots(serial) {
        const query = serial ? `?${new URLSearchParams({ serial }).toString()}` : "";
        return this.request(`/api/v1/storage/android-roots${query}`);
    }
    async autoDownload() {
        return this.request("/api/v1/auto-download");
    }
    async configureAutoDownload(config) {
        return this.request("/api/v1/auto-download", {
            method: "PUT",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(config),
        });
    }
    async scanAutoDownload() {
        return this.request("/api/v1/auto-download/scan", { method: "POST" });
    }
    async resetAutoDownload() {
        return this.request("/api/v1/auto-download/reset", { method: "POST" });
    }
    async destinationProfiles() {
        return this.request("/api/v1/destination-profiles");
    }
    async transfers() {
        return this.request("/api/v1/transfers");
    }
    async openDestinationProfile(profileId) {
        return this.request(`/api/v1/destination-profiles/${encodeURIComponent(profileId)}/open`, { method: "POST" });
    }
    async openDestinationPath(path) {
        return this.request("/api/v1/destination-path/open", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ path }),
        });
    }
    async uploadFile(request) {
        const form = new FormData();
        form.set("serial", request.serial);
        form.set("file", request.file, request.file.name);
        // Omitted on purpose for inbox drops: the server owns the default upload
        // directory, so the client must not duplicate that path.
        if (request.destinationPath !== undefined)
            form.set("destinationPath", request.destinationPath);
        form.set("duplicatePolicy", request.duplicatePolicy);
        return this.request("/api/v1/transfers/upload", { method: "POST", body: form });
    }
    async downloadFile(request) {
        return this.request("/api/v1/transfers/download", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify(request),
        });
    }
    async cancelTransfer(transferId) {
        return this.request(`/api/v1/transfers/${encodeURIComponent(transferId)}/cancel`, { method: "POST" });
    }
    async retryTransfer(transferId) {
        return this.request(`/api/v1/transfers/${encodeURIComponent(transferId)}/retry`, { method: "POST" });
    }
    async recordVirtualResize(sessionId, width, height) {
        return this.request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/virtual-display/resize`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ width, height }),
        });
    }
    async recordApplicationLaunch(sessionId, result) {
        return this.request(`/api/v1/sessions/${encodeURIComponent(sessionId)}/virtual-display/application-launch`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ result }),
        });
    }
    async getSession(sessionId) {
        return this.request(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
    }
    async stopSession(sessionId, keepalive = false) {
        try {
            return await this.request(`/api/v1/sessions/${encodeURIComponent(sessionId)}`, {
                method: "DELETE",
                keepalive,
            });
        }
        catch (error) {
            if (keepalive)
                return null;
            throw error;
        }
    }
    async networkStatus() {
        return this.request("/api/v1/network/status");
    }
    async networkInterfaces() {
        return this.request("/api/v1/network/interfaces");
    }
    async networkConfig() {
        return this.request("/api/v1/network/config");
    }
    async validateNetworkConfig(config) {
        return this.request("/api/v1/network/validate", {
            method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(config),
        });
    }
    async applyNetworkConfig(config) {
        return this.request("/api/v1/network/apply", {
            method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(config),
        });
    }
    async disableNetworkAccess(currentPin) {
        return this.request("/api/v1/network/disable", {
            method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ currentPin }),
        });
    }
    async request(path, init, publicRequest = false) {
        const method = (init?.method ?? "GET").toUpperCase();
        const headers = new Headers(init?.headers);
        if (!publicRequest && !["GET", "HEAD", "OPTIONS"].includes(method) && sharedCsrfToken) {
            headers.set("x-droidwebdisplay-csrf", sharedCsrfToken);
        }
        const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
            ...init,
            headers,
            credentials: "same-origin",
        });
        const contentType = response.headers.get("content-type") ?? "";
        const payload = contentType.includes("application/json") ? await response.json() : await response.text();
        if (!response.ok) {
            if (response.status === 401 && !publicRequest) {
                setSharedCsrfToken(null);
                globalThis.dispatchEvent?.(new CustomEvent("droidwebdisplay-auth-required"));
            }
            const message = typeof payload === "object" && payload !== null && "error" in payload
                ? String(payload.error?.message ?? response.statusText)
                : `${response.status} ${response.statusText}`;
            throw new BridgeApiError(message, response.status, payload);
        }
        return payload;
    }
}
//# sourceMappingURL=api.js.map