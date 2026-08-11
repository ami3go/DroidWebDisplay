import { BridgeApi, BridgeApiError } from "./api.js";
export class NetworkAccessController {
    elements;
    #api;
    #interfaces = [];
    #activeUrl = "http://127.0.0.1:8765";
    constructor(elements, api = new BridgeApi()) {
        this.elements = elements;
        this.#api = api;
        elements.mode.addEventListener("change", () => this.#syncVisibility());
        elements.interfaceSelect.addEventListener("change", () => this.#selectInterface());
        elements.certificateSource.addEventListener("change", () => this.#syncVisibility());
        elements.validate.addEventListener("click", () => void this.#run(() => this.#validate()));
        elements.apply.addEventListener("click", () => void this.#run(() => this.#apply()));
        elements.disable.addEventListener("click", () => void this.#run(() => this.#disable()));
        elements.copyUrl.addEventListener("click", () => void this.#copyUrl());
    }
    async initialize() {
        this.elements.card.hidden = false;
        const [interfaces, stored, status] = await Promise.all([
            this.#api.networkInterfaces(),
            this.#api.networkConfig(),
            this.#api.networkStatus(),
        ]);
        this.#interfaces = interfaces.interfaces;
        this.#renderInterfaces();
        this.#loadConfig(stored.config);
        this.#activeUrl = status.url;
        this.elements.url.textContent = status.url;
        this.elements.downloadCertificate.hidden = !status.lanEnabled;
        this.elements.disable.disabled = !status.lanEnabled;
        this.elements.badge.textContent = status.lanEnabled ? "LAN HTTPS" : "Local only";
        this.elements.badge.classList.toggle("lan-enabled", status.lanEnabled);
        this.elements.status.textContent = status.lanEnabled
            ? `LAN access is active at ${status.url}. Authentication is required.`
            : "Local-only access is active.";
        this.#syncVisibility();
    }
    #renderInterfaces() {
        this.elements.interfaceSelect.replaceChildren(new Option("Select an active private interface", ""));
        for (const item of this.#interfaces) {
            const label = `${item.name} · ${item.address} · ${item.network}${item.adapterType === "vpn" || item.adapterType === "virtual" ? ` · ${item.adapterType}` : ""}`;
            this.elements.interfaceSelect.add(new Option(label, item.address));
        }
    }
    #loadConfig(config) {
        this.elements.mode.value = config.mode;
        this.elements.port.value = String(config.port);
        this.elements.bindAddress.value = config.bindAddress;
        this.elements.allowedNetworks.value = config.allowedNetworks.join(", ");
        this.elements.hostname.value = config.hostname ?? "";
        this.elements.certificateSource.value = config.tls?.certificateSource === "existing" ? "existing" : "generated";
        this.elements.certificatePath.value = config.tls?.certificatePath ?? "";
        this.elements.privateKeyPath.value = "";
        this.elements.manageFirewall.checked = config.firewall?.manageRule ?? false;
        const matching = this.#interfaces.find((item) => item.address === config.bindAddress);
        this.elements.interfaceSelect.value = matching?.address ?? "";
    }
    #syncVisibility() {
        const lan = this.elements.mode.value === "lan-https";
        const existing = this.elements.certificateSource.value === "existing";
        this.elements.lanFields.hidden = !lan;
        this.elements.warning.hidden = !lan;
        this.elements.existingCertificate.hidden = !lan || !existing;
        this.elements.validityRow.hidden = !lan || existing;
        this.elements.copyUrl.disabled = !lan && !this.elements.badge.classList.contains("lan-enabled");
    }
    #selectInterface() {
        const selected = this.#interfaces.find((item) => item.address === this.elements.interfaceSelect.value);
        if (!selected)
            return;
        this.elements.bindAddress.value = selected.address;
        this.elements.allowedNetworks.value = selected.network;
    }
    #request() {
        const mode = this.elements.mode.value;
        const port = Number.parseInt(this.elements.port.value, 10);
        if (!Number.isInteger(port) || port < 1 || port > 65535)
            throw new Error("Port must be between 1 and 65535.");
        const pin = this.elements.currentPin.value.trim();
        if (!/^\d{4,12}$/.test(pin))
            throw new Error("Enter the current 4–12 digit PIN.");
        const allowedNetworks = this.elements.allowedNetworks.value.split(/[;,\s]+/).map((item) => item.trim()).filter(Boolean);
        if (mode === "lan-https" && !this.elements.bindAddress.value)
            throw new Error("Select a private network interface.");
        return {
            mode,
            bindAddress: mode === "local-only" ? "127.0.0.1" : this.elements.bindAddress.value,
            port,
            allowedNetworks: mode === "local-only" ? [] : allowedNetworks,
            hostname: this.elements.hostname.value.trim() || undefined,
            certificateSource: this.elements.certificateSource.value,
            certificatePath: this.elements.certificatePath.value.trim() || undefined,
            privateKeyPath: this.elements.privateKeyPath.value.trim() || undefined,
            certificateValidityDays: Number.parseInt(this.elements.certificateValidity.value, 10),
            manageFirewall: mode === "lan-https" && this.elements.manageFirewall.checked,
            currentPin: pin,
        };
    }
    async #validate() {
        await this.#api.validateNetworkConfig(this.#request());
        this.elements.status.textContent = "Network configuration is valid. Apply it to restart the service.";
    }
    async #apply() {
        const request = this.#request();
        const warning = request.mode === "lan-https"
            ? `Enable authenticated HTTPS access on ${request.bindAddress}:${request.port}? Existing trusted sessions will be revoked.`
            : "Return to local-only access? Existing trusted sessions will be revoked.";
        if (!globalThis.confirm(warning))
            return;
        const result = await this.#api.applyNetworkConfig(request);
        this.elements.currentPin.value = "";
        this.elements.status.textContent = `Configuration saved. Service is restarting. Reopen ${result.url}`;
        this.elements.url.textContent = result.url;
        this.#activeUrl = result.url;
        if (result.restartScheduled) {
            globalThis.setTimeout(() => globalThis.location.assign(result.url), 2500);
        }
    }
    async #disable() {
        const pin = this.elements.currentPin.value.trim();
        if (!/^\d{4,12}$/.test(pin))
            throw new Error("Enter the current PIN before disabling LAN access.");
        if (!globalThis.confirm("Disable LAN access and return to local-only mode? Existing trusted sessions will be revoked."))
            return;
        const result = await this.#api.disableNetworkAccess(pin);
        this.elements.status.textContent = `LAN access disabled. Reopen ${result.url} on this PC after restart.`;
        this.elements.url.textContent = result.url;
        if (result.restartScheduled)
            globalThis.setTimeout(() => globalThis.location.assign(result.url), 2500);
    }
    async #copyUrl() {
        const value = this.elements.url.textContent?.trim() || this.#activeUrl;
        try {
            await navigator.clipboard.writeText(value);
            this.elements.status.textContent = `Copied ${value}`;
        }
        catch {
            this.elements.status.textContent = `LAN URL: ${value}`;
        }
    }
    async #run(action) {
        this.elements.validate.disabled = true;
        this.elements.apply.disabled = true;
        this.elements.disable.disabled = true;
        try {
            await action();
        }
        catch (error) {
            this.elements.status.textContent = error instanceof BridgeApiError ? error.message : String(error);
        }
        finally {
            this.elements.validate.disabled = false;
            this.elements.apply.disabled = false;
            this.elements.disable.disabled = !this.elements.badge.classList.contains("lan-enabled");
        }
    }
}
//# sourceMappingURL=network-controller.js.map