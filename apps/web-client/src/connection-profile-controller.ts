interface ConnectionProfileDevice {
  serial: string;
  model: string | null;
}

interface ConnectionProfileDisplay {
  displayMode: "physical" | "virtual";
  profileId: string;
  sizeMode: "fixed" | "flex";
  width: number;
  height: number;
  dpi: number;
  startApp: string;
  forceStopBeforeLaunch: boolean;
  keepActive: boolean;
  systemDecorations: boolean;
  destroyContentOnClose: boolean;
  imePolicy: "default" | "local" | "fallback" | "hide";
  preserveAspectRatio: boolean;
  videoBitRateMbps: number;
  maxFps: number;
}

interface ConnectionProfileInput {
  name: string;
  device: ConnectionProfileDevice;
  display: ConnectionProfileDisplay;
  audio: { enabled: boolean; muted: boolean; volume: number };
  clipboard: { automatic: boolean; maximumKiB: number };
  reconnect: { enabled: boolean; attempts: 3 | 5 | 10 };
  video: { encoderMode: "auto" | "selected"; encoder: string | null };
}

interface StoredConnectionProfile extends ConnectionProfileInput {
  schemaVersion: 1;
  id: string;
  createdAt: string;
  updatedAt: string;
  lastUsedAt: string | null;
}

interface ProfileListResponse {
  schemaVersion: 1;
  defaultProfileId: string | null;
  profiles: StoredConnectionProfile[];
}

interface AndroidDeviceDto {
  serial: string;
  model?: string | null;
  ready?: boolean;
  state?: string;
}

interface EncoderInfo {
  encoders?: string[];
  preference?: string | null;
}

interface VirtualDisplayCapabilitiesDto {
  virtualDisplaySupported: boolean;
  localImePolicySupported: boolean;
  requestedAppInstalled: boolean | null;
  warnings: string[];
}

interface PortableProfileDocument {
  kind: "droidwebdisplay-connection-profile";
  exportVersion: 1;
  profileSchemaVersion: 1;
  profile: ConnectionProfileInput;
}

const PROFILE_EXPORT_KIND = "droidwebdisplay-connection-profile";
const PROFILE_EXPORT_VERSION = 1;
const PROFILE_SCHEMA_VERSION = 1;

const PROFILE_INPUT_IDS = new Set([
  "device", "display-mode", "display-profile", "virtual-size-mode", "virtual-width", "virtual-height", "virtual-dpi",
  "virtual-app-package", "virtual-force-stop", "virtual-keep-active", "virtual-system-decorations", "virtual-destroy-content",
  "virtual-ime-policy", "virtual-hide-keyboard", "virtual-preserve-aspect", "virtual-bitrate", "virtual-max-fps", "audio-enabled",
  "audio-volume", "clipboard-auto-sync", "clipboard-max-kib", "auto-reconnect", "reconnect-attempts", "latency-video-encoder",
]);

class ProfileDeviceUnavailableError extends Error {
  public constructor(public readonly profile: StoredConnectionProfile) {
    super(`Saved Android device is not available: ${profile.device.model ?? profile.device.serial} · ${profile.device.serial}`);
  }
}

function element<T extends HTMLElement>(id: string): T {
  const value = document.getElementById(id);
  if (!value) throw new Error(`Missing profile UI dependency: #${id}`);
  return value as T;
}

function optionalElement<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}

function dispatchChange(target: HTMLElement): void {
  target.dispatchEvent(new Event("change", { bubbles: true }));
}

function dispatchInput(target: HTMLElement): void {
  target.dispatchEvent(new Event("input", { bubbles: true }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function inputFromUnknown(value: unknown): ConnectionProfileInput {
  if (!isRecord(value)) throw new Error("Connection profile file must contain a JSON object.");
  const schemaVersion = value.schemaVersion;
  if (typeof schemaVersion === "number" && schemaVersion > PROFILE_SCHEMA_VERSION) {
    throw new Error("This profile was created by a newer DroidWebDisplay version.");
  }
  const required = ["name", "device", "display", "audio", "clipboard", "reconnect", "video"];
  for (const key of required) if (!(key in value)) throw new Error(`Connection profile is missing '${key}'.`);
  return {
    name: String(value.name),
    device: value.device as ConnectionProfileDevice,
    display: value.display as ConnectionProfileDisplay,
    audio: value.audio as ConnectionProfileInput["audio"],
    clipboard: value.clipboard as ConnectionProfileInput["clipboard"],
    reconnect: value.reconnect as ConnectionProfileInput["reconnect"],
    video: value.video as ConnectionProfileInput["video"],
  };
}

export function parsePortableConnectionProfile(value: unknown): ConnectionProfileInput {
  if (!isRecord(value)) throw new Error("Connection profile file must contain a JSON object.");
  if (value.kind === PROFILE_EXPORT_KIND) {
    const exportVersion = Number(value.exportVersion);
    const profileSchemaVersion = Number(value.profileSchemaVersion);
    if (exportVersion > PROFILE_EXPORT_VERSION || profileSchemaVersion > PROFILE_SCHEMA_VERSION) {
      throw new Error("This profile was created by a newer DroidWebDisplay version.");
    }
    if (exportVersion !== PROFILE_EXPORT_VERSION || profileSchemaVersion !== PROFILE_SCHEMA_VERSION) {
      throw new Error("Unsupported connection profile file version.");
    }
    return inputFromUnknown(value.profile);
  }
  return inputFromUnknown(value);
}

export function portableConnectionProfile(profile: StoredConnectionProfile): PortableProfileDocument {
  return {
    kind: PROFILE_EXPORT_KIND,
    exportVersion: PROFILE_EXPORT_VERSION,
    profileSchemaVersion: PROFILE_SCHEMA_VERSION,
    profile: profileInput(profile),
  };
}

async function waitUntil(predicate: () => boolean, timeoutMs: number, intervalMs = 75): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) return true;
    await new Promise(resolve => window.setTimeout(resolve, intervalMs));
  }
  return predicate();
}

async function csrfToken(): Promise<string> {
  const response = await fetch("/api/v1/auth/status", { cache: "no-store" });
  if (!response.ok) throw new Error(`Authentication status failed (${response.status})`);
  const body = await response.json() as { csrfToken?: string };
  if (!body.csrfToken) throw new Error("Authenticated CSRF token is unavailable");
  return body.csrfToken;
}

async function requestJson<T>(url: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  const method = String(options.method ?? "GET").toUpperCase();
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) headers.set("X-DroidWebDisplay-CSRF", await csrfToken());
  const response = await fetch(url, { ...options, headers, cache: "no-store" });
  const body = await response.json().catch(() => ({})) as { detail?: string };
  if (!response.ok) throw new Error(body.detail ?? `Request failed (${response.status})`);
  return body as T;
}

function profileInput(profile: StoredConnectionProfile): ConnectionProfileInput {
  return {
    name: profile.name,
    device: { ...profile.device },
    display: { ...profile.display },
    audio: { ...profile.audio },
    clipboard: { ...profile.clipboard },
    reconnect: { ...profile.reconnect },
    video: { ...profile.video },
  };
}

export class ConnectionProfileController {
  #profiles: StoredConnectionProfile[] = [];
  #defaultProfileId: string | null = null;
  #selectedProfileId: string | null = null;
  #dirty = false;
  #applying = false;
  #initialized = false;
  #waitingProfileId: string | null = null;
  #waitingGeneration = 0;
  #waitingTimer: number | null = null;

  public async initialize(): Promise<void> {
    if (this.#initialized) return;
    this.installUi();
    this.renameDisplayPresetUi();
    this.bindUi();
    this.bindDirtyTracking();
    await this.refreshProfiles();
    this.#initialized = true;
    const startup = this.#defaultProfileId ? this.#profiles.find(profile => profile.id === this.#defaultProfileId) : null;
    if (startup) window.setTimeout(() => void this.run(() => this.loadAndConnectProfile(startup, true)), 0);
  }

  private installUi(): void {
    const card = document.querySelector<HTMLElement>('.gb-drawer-slot[data-slot="settings"] .settings-card');
    if (!card || document.getElementById("connection-profile-panel")) return;
    const panel = document.createElement("div");
    panel.id = "connection-profile-panel";
    panel.className = "connection-profile-panel";
    panel.innerHTML = `
      <h3>Connection profiles</h3>
      <p>Save the selected Android device together with display, audio, clipboard, reconnect and video-encoder settings.</p>
      <label>Connection profile
        <select id="connection-profile-select"><option value="">No saved profiles</option></select>
      </label>
      <button id="connection-profile-load" type="button" disabled>Load &amp; Connect</button>
      <button id="connection-profile-cancel-wait" type="button" class="secondary" hidden>Cancel waiting</button>
      <div class="two-button-row uniform-buttons">
        <button id="connection-profile-save" type="button" class="secondary">Save current</button>
        <button id="connection-profile-update" type="button" class="secondary" disabled>Update</button>
      </div>
      <div class="two-button-row uniform-buttons">
        <button id="connection-profile-rename" type="button" class="secondary" disabled>Rename</button>
        <button id="connection-profile-delete" type="button" class="danger" disabled>Delete</button>
      </div>
      <div class="two-button-row uniform-buttons">
        <button id="connection-profile-export" type="button" class="secondary" disabled>Export profile</button>
        <button id="connection-profile-import" type="button" class="secondary">Import profile</button>
      </div>
      <input id="connection-profile-file" type="file" accept="application/json,.json" hidden>
      <label class="toggle-row"><input id="connection-profile-default" type="checkbox" disabled> Auto-load this profile at startup</label>
      <p id="connection-profile-meta" class="running-app-status">No connection profile selected.</p>
      <p id="connection-profile-status" class="running-app-status">Profiles are stored by this DroidWebDisplay service.</p>
      <hr>`;
    card.prepend(panel);
  }

  private renameDisplayPresetUi(): void {
    const select = optionalElement<HTMLSelectElement>("display-profile");
    const label = select?.closest("label");
    if (label?.firstChild?.nodeType === Node.TEXT_NODE) label.firstChild.textContent = "Display preset\n              ";
    const restore = optionalElement<HTMLButtonElement>("restore-profile");
    if (restore) restore.textContent = "Restore preset settings";
  }

  private bindUi(): void {
    element<HTMLSelectElement>("connection-profile-select").addEventListener("change", () => this.selectProfile());
    element<HTMLButtonElement>("connection-profile-load").addEventListener("click", () => void this.run(() => this.loadAndConnectSelected()));
    element<HTMLButtonElement>("connection-profile-cancel-wait").addEventListener("click", () => this.cancelWaiting(true));
    element<HTMLButtonElement>("connection-profile-save").addEventListener("click", () => void this.run(() => this.saveCurrent()));
    element<HTMLButtonElement>("connection-profile-update").addEventListener("click", () => void this.run(() => this.updateCurrent()));
    element<HTMLButtonElement>("connection-profile-rename").addEventListener("click", () => void this.run(() => this.renameSelected()));
    element<HTMLButtonElement>("connection-profile-delete").addEventListener("click", () => void this.run(() => this.deleteSelected()));
    element<HTMLButtonElement>("connection-profile-export").addEventListener("click", () => void this.run(() => this.exportSelected()));
    element<HTMLButtonElement>("connection-profile-import").addEventListener("click", () => element<HTMLInputElement>("connection-profile-file").click());
    element<HTMLInputElement>("connection-profile-file").addEventListener("change", () => void this.run(() => this.importSelectedFile()));
    element<HTMLInputElement>("connection-profile-default").addEventListener("change", () => void this.run(() => this.changeDefault()));
  }

  private bindDirtyTracking(): void {
    const onEdit = (event: Event) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.id && PROFILE_INPUT_IDS.has(target.id)) this.markDirty();
    };
    document.addEventListener("input", onEdit);
    document.addEventListener("change", onEdit);
    optionalElement<HTMLButtonElement>("audio-mute")?.addEventListener("click", () => window.setTimeout(() => this.markDirty(), 0));
  }

  private markDirty(): void {
    if (this.#applying || !this.#selectedProfileId) return;
    this.#dirty = true;
    this.renderSelectionState();
  }

  private async refreshProfiles(preferredId?: string | null): Promise<void> {
    const data = await requestJson<ProfileListResponse>("/api/v1/profiles");
    this.#profiles = data.profiles;
    this.#defaultProfileId = data.defaultProfileId;
    const select = element<HTMLSelectElement>("connection-profile-select");
    select.replaceChildren();
    if (!this.#profiles.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No saved profiles";
      select.append(option);
      this.#selectedProfileId = null;
    } else {
      for (const profile of this.#profiles) {
        const option = document.createElement("option");
        option.value = profile.id;
        option.textContent = profile.name;
        select.append(option);
      }
      const desired = preferredId ?? this.#selectedProfileId ?? this.#defaultProfileId ?? this.#profiles[0]!.id;
      const selected = this.#profiles.some(profile => profile.id === desired) ? desired : this.#profiles[0]!.id;
      select.value = selected;
      this.#selectedProfileId = selected;
    }
    this.#dirty = false;
    this.renderSelectionState();
  }

  private selectProfile(): void {
    const value = element<HTMLSelectElement>("connection-profile-select").value;
    if (this.#waitingProfileId && value !== this.#waitingProfileId) {
      this.cancelWaiting(false);
      this.setStatus("Waiting cancelled because another connection profile was selected.");
    }
    this.#selectedProfileId = value || null;
    this.#dirty = false;
    this.renderSelectionState();
  }

  private selectedProfile(): StoredConnectionProfile | null {
    return this.#profiles.find(profile => profile.id === this.#selectedProfileId) ?? null;
  }

  private renderSelectionState(): void {
    const profile = this.selectedProfile();
    const hasProfile = profile !== null;
    element<HTMLButtonElement>("connection-profile-load").disabled = !hasProfile || this.#waitingProfileId !== null;
    element<HTMLButtonElement>("connection-profile-update").disabled = !hasProfile || !this.#dirty;
    element<HTMLButtonElement>("connection-profile-rename").disabled = !hasProfile;
    element<HTMLButtonElement>("connection-profile-delete").disabled = !hasProfile;
    element<HTMLButtonElement>("connection-profile-export").disabled = !hasProfile;
    const defaultToggle = element<HTMLInputElement>("connection-profile-default");
    defaultToggle.disabled = !hasProfile;
    defaultToggle.checked = Boolean(profile && profile.id === this.#defaultProfileId);
    const meta = element<HTMLElement>("connection-profile-meta");
    if (!profile) {
      meta.textContent = "No connection profile selected.";
      return;
    }
    const selectedOption = element<HTMLSelectElement>("connection-profile-select").selectedOptions[0];
    if (selectedOption) selectedOption.textContent = `${profile.name}${this.#dirty ? " *" : ""}`;
    const used = profile.lastUsedAt ? new Date(profile.lastUsedAt).toLocaleString() : "never";
    const defaultText = profile.id === this.#defaultProfileId ? " · startup default" : "";
    const waiting = profile.id === this.#waitingProfileId ? " · waiting for device" : "";
    meta.textContent = `${profile.device.model ?? profile.device.serial} · ${profile.device.serial} · last used ${used}${defaultText}${waiting}${this.#dirty ? " · modified" : ""}`;
  }

  private async currentDevice(): Promise<ConnectionProfileDevice> {
    const serial = element<HTMLSelectElement>("device").value;
    if (!serial) throw new Error("Select an authorized Android device before saving a connection profile.");
    const response = await requestJson<{ devices: AndroidDeviceDto[] }>("/api/v1/devices");
    const device = response.devices.find(item => item.serial === serial);
    return { serial, model: device?.model ?? null };
  }

  private reconnectAttempts(): 3 | 5 | 10 {
    const value = Number(element<HTMLSelectElement>("reconnect-attempts").value);
    return value === 3 || value === 10 ? value : 5;
  }

  private async captureCurrent(name: string): Promise<ConnectionProfileInput> {
    const encoder = optionalElement<HTMLSelectElement>("latency-video-encoder")?.value || null;
    const hideKeyboard = element<HTMLInputElement>("virtual-hide-keyboard").checked;
    const ime = element<HTMLSelectElement>("virtual-ime-policy").value;
    return {
      name,
      device: await this.currentDevice(),
      display: {
        displayMode: element<HTMLSelectElement>("display-mode").value === "virtual" ? "virtual" : "physical",
        profileId: element<HTMLSelectElement>("display-profile").value || "custom",
        sizeMode: element<HTMLSelectElement>("virtual-size-mode").value === "flex" ? "flex" : "fixed",
        width: Number(element<HTMLInputElement>("virtual-width").value), height: Number(element<HTMLInputElement>("virtual-height").value),
        dpi: Number(element<HTMLInputElement>("virtual-dpi").value), startApp: element<HTMLInputElement>("virtual-app-package").value.trim(),
        forceStopBeforeLaunch: element<HTMLInputElement>("virtual-force-stop").checked, keepActive: element<HTMLInputElement>("virtual-keep-active").checked,
        systemDecorations: element<HTMLInputElement>("virtual-system-decorations").checked,
        destroyContentOnClose: element<HTMLInputElement>("virtual-destroy-content").checked,
        imePolicy: hideKeyboard ? "hide" : (["local", "fallback"].includes(ime) ? ime as "local" | "fallback" : "default"),
        preserveAspectRatio: element<HTMLInputElement>("virtual-preserve-aspect").checked,
        videoBitRateMbps: Number(element<HTMLInputElement>("virtual-bitrate").value), maxFps: Number(element<HTMLInputElement>("virtual-max-fps").value),
      },
      audio: { enabled: element<HTMLInputElement>("audio-enabled").checked, muted: element<HTMLButtonElement>("audio-mute").textContent === "Unmute", volume: clamp(Number(element<HTMLInputElement>("audio-volume").value), 0, 100) },
      clipboard: { automatic: element<HTMLInputElement>("clipboard-auto-sync").checked, maximumKiB: clamp(Number(element<HTMLInputElement>("clipboard-max-kib").value), 1, 256) },
      reconnect: { enabled: element<HTMLInputElement>("auto-reconnect").checked, attempts: this.reconnectAttempts() },
      video: encoder ? { encoderMode: "selected", encoder } : { encoderMode: "auto", encoder: null },
    };
  }

  private async loadAndConnectSelected(): Promise<void> {
    const profile = this.selectedProfile();
    if (!profile) throw new Error("Select a connection profile first.");
    await this.loadAndConnectProfile(profile, true);
  }

  private async loadAndConnectProfile(profile: StoredConnectionProfile, waitIfMissing: boolean): Promise<void> {
    this.cancelWaiting(false);
    const disconnect = element<HTMLButtonElement>("disconnect");
    if (!disconnect.disabled) {
      this.setStatus("Disconnecting the current Android session before loading the profile…");
      disconnect.click();
      if (!await waitUntil(() => disconnect.disabled, 10_000)) throw new Error("Timed out while disconnecting the current Android session.");
    }
    this.#applying = true;
    try {
      this.applyProfileSettings(profile);
      try {
        await this.selectExactDevice(profile);
      } catch (error) {
        if (waitIfMissing && error instanceof ProfileDeviceUnavailableError) {
          this.beginWaiting(profile);
          return;
        }
        throw error;
      }
      await this.finishProfileConnection(profile);
    } finally {
      this.#applying = false;
    }
  }

  private async finishProfileConnection(profile: StoredConnectionProfile): Promise<void> {
    const encoderWarning = await this.applyEncoderPreference(profile);
    await this.validateVirtualCapability(profile);
    this.#dirty = false;
    this.renderSelectionState();
    this.setMainStatus("Connecting profile", `${profile.name} · ${profile.device.model ?? profile.device.serial}`);
    this.setStatus(`Connecting ${profile.name}…${encoderWarning ? ` ${encoderWarning}` : ""}`);
    const connect = element<HTMLButtonElement>("connect");
    if (!await waitUntil(() => !connect.disabled, 8_000, 100)) throw new Error("The restored profile is not currently connectable. Check device capability and display settings.");
    connect.click();
    const connected = await waitUntil(() => element<HTMLElement>("connection-status").dataset.state === "connected", 20_000, 100);
    if (!connected) throw new Error(`Timed out connecting profile '${profile.name}'.`);
    await requestJson<StoredConnectionProfile>(`/api/v1/profiles/${encodeURIComponent(profile.id)}/used`, { method: "POST" });
    await this.refreshProfiles(profile.id);
    this.setMainStatus("Profile connected", `${profile.name} · ${profile.device.model ?? profile.device.serial}`);
    this.setStatus(`Profile connected: ${profile.name}.${encoderWarning ? ` ${encoderWarning}` : ""}`);
  }

  private applyProfileSettings(profile: StoredConnectionProfile): void {
    const display = profile.display;
    const displayMode = element<HTMLSelectElement>("display-mode"); displayMode.value = display.displayMode; dispatchChange(displayMode);
    const displayProfile = element<HTMLSelectElement>("display-profile");
    const savedPresetExists = [...displayProfile.options].some(option => option.value === display.profileId);
    displayProfile.value = savedPresetExists ? display.profileId : "custom";
    element<HTMLSelectElement>("virtual-size-mode").value = display.sizeMode;
    element<HTMLInputElement>("virtual-width").value = String(display.width); element<HTMLInputElement>("virtual-height").value = String(display.height);
    element<HTMLInputElement>("virtual-dpi").value = String(display.dpi); element<HTMLInputElement>("virtual-app-package").value = display.startApp;
    element<HTMLInputElement>("virtual-force-stop").checked = display.forceStopBeforeLaunch; element<HTMLInputElement>("virtual-keep-active").checked = display.keepActive;
    element<HTMLInputElement>("virtual-system-decorations").checked = display.systemDecorations; element<HTMLInputElement>("virtual-destroy-content").checked = display.destroyContentOnClose;
    element<HTMLInputElement>("virtual-hide-keyboard").checked = display.imePolicy === "hide";
    element<HTMLSelectElement>("virtual-ime-policy").value = display.imePolicy === "hide" ? "default" : display.imePolicy;
    element<HTMLInputElement>("virtual-preserve-aspect").checked = display.preserveAspectRatio;
    element<HTMLInputElement>("virtual-bitrate").value = String(display.videoBitRateMbps); element<HTMLInputElement>("virtual-max-fps").value = String(display.maxFps);
    dispatchInput(element<HTMLInputElement>("virtual-width")); displayProfile.value = savedPresetExists ? display.profileId : "custom";
    const audioEnabled = element<HTMLInputElement>("audio-enabled"); audioEnabled.checked = profile.audio.enabled; dispatchChange(audioEnabled);
    element<HTMLInputElement>("audio-volume").value = String(profile.audio.volume); element<HTMLButtonElement>("audio-mute").textContent = profile.audio.muted ? "Unmute" : "Mute";
    const clipboard = element<HTMLInputElement>("clipboard-auto-sync"); clipboard.checked = profile.clipboard.automatic; dispatchChange(clipboard);
    element<HTMLInputElement>("clipboard-max-kib").value = String(profile.clipboard.maximumKiB); dispatchChange(element<HTMLInputElement>("clipboard-max-kib"));
    const reconnect = element<HTMLInputElement>("auto-reconnect"); reconnect.checked = profile.reconnect.enabled; dispatchChange(reconnect);
    const reconnectAttempts = element<HTMLSelectElement>("reconnect-attempts"); reconnectAttempts.value = String(profile.reconnect.attempts); dispatchChange(reconnectAttempts);
  }

  private async selectExactDevice(profile: StoredConnectionProfile): Promise<void> {
    const devices = await requestJson<{ devices: AndroidDeviceDto[] }>("/api/v1/devices");
    const saved = devices.devices.find(device => device.serial === profile.device.serial);
    if (!saved || saved.ready === false || (saved.state && saved.state !== "device")) throw new ProfileDeviceUnavailableError(profile);
    element<HTMLButtonElement>("refresh").click();
    const select = element<HTMLSelectElement>("device");
    const appeared = await waitUntil(() => [...select.options].some(option => option.value === profile.device.serial && !option.disabled), 5_000);
    if (!appeared) throw new ProfileDeviceUnavailableError(profile);
    select.value = profile.device.serial;
    if (profile.display.displayMode === "virtual") element<HTMLElement>("virtual-capability").textContent = "Checking saved profile device capabilities…";
    dispatchChange(select);
  }

  private async applyEncoderPreference(profile: StoredConnectionProfile): Promise<string | null> {
    const serial = encodeURIComponent(profile.device.serial);
    if (profile.video.encoderMode === "auto" || !profile.video.encoder) {
      await requestJson(`/api/v1/devices/${serial}/video-encoder`, { method: "PUT", body: JSON.stringify({ encoder: null }) });
      const select = optionalElement<HTMLSelectElement>("latency-video-encoder"); if (select) select.value = ""; return null;
    }
    try {
      const info = await requestJson<EncoderInfo>(`/api/v1/devices/${serial}/video-encoders`);
      if (Array.isArray(info.encoders) && info.encoders.length > 0 && !info.encoders.includes(profile.video.encoder)) {
        await requestJson(`/api/v1/devices/${serial}/video-encoder`, { method: "PUT", body: JSON.stringify({ encoder: null }) });
        return `Saved encoder '${profile.video.encoder}' is no longer available; using Auto.`;
      }
      await requestJson(`/api/v1/devices/${serial}/video-encoder`, { method: "PUT", body: JSON.stringify({ encoder: profile.video.encoder }) });
      const select = optionalElement<HTMLSelectElement>("latency-video-encoder");
      if (select && [...select.options].some(option => option.value === profile.video.encoder)) select.value = profile.video.encoder;
      return null;
    } catch {
      await requestJson(`/api/v1/devices/${serial}/video-encoder`, { method: "PUT", body: JSON.stringify({ encoder: null }) });
      return `Saved encoder '${profile.video.encoder}' could not be restored; using Auto.`;
    }
  }

  private async validateVirtualCapability(profile: StoredConnectionProfile): Promise<void> {
    if (profile.display.displayMode !== "virtual") return;
    const serial = encodeURIComponent(profile.device.serial);
    const query = new URLSearchParams({ startApp: profile.display.startApp });
    const capabilities = await requestJson<VirtualDisplayCapabilitiesDto>(`/api/v1/devices/${serial}/virtual-display-capabilities?${query.toString()}`);
    if (!capabilities.virtualDisplaySupported) throw new Error(capabilities.warnings.join(" ") || "The saved device no longer supports virtual display mode.");
    if (profile.display.startApp && capabilities.requestedAppInstalled === false) {
      if (!profile.display.systemDecorations) throw new Error(`Saved application '${profile.display.startApp}' is no longer installed and system decorations are disabled.`);
      const accepted = window.confirm(`Saved application '${profile.display.startApp}' is no longer installed. Connect without launching it?`);
      if (!accepted) throw new Error("Connection cancelled because the saved application is unavailable.");
      element<HTMLInputElement>("virtual-app-package").value = ""; dispatchInput(element<HTMLInputElement>("virtual-app-package"));
    }
    if (profile.display.imePolicy === "local" && !capabilities.localImePolicySupported) {
      const accepted = window.confirm("This Android build does not support the saved Local IME policy. Use Android default IME for this connection?");
      if (!accepted) throw new Error("Connection cancelled because the saved Local IME policy is unavailable.");
      element<HTMLSelectElement>("virtual-ime-policy").value = "default"; dispatchChange(element<HTMLSelectElement>("virtual-ime-policy"));
    }
    const capability = element<HTMLElement>("virtual-capability");
    await waitUntil(() => capability.textContent !== "Checking saved profile device capabilities…", 8_000, 100);
  }

  private beginWaiting(profile: StoredConnectionProfile): void {
    this.cancelWaiting(false); this.#waitingProfileId = profile.id; this.#waitingGeneration += 1;
    const generation = this.#waitingGeneration; element<HTMLButtonElement>("connection-profile-cancel-wait").hidden = false;
    this.setMainStatus("Waiting for profile device", `${profile.name} · ${profile.device.model ?? profile.device.serial} · ${profile.device.serial}`);
    this.setStatus(`Waiting for exact saved device: ${profile.device.model ?? profile.device.serial} · ${profile.device.serial}.`);
    this.renderSelectionState(); this.#waitingTimer = window.setTimeout(() => void this.pollWaitingProfile(profile, generation), 1000);
  }

  private async pollWaitingProfile(profile: StoredConnectionProfile, generation: number): Promise<void> {
    if (this.#waitingProfileId !== profile.id || generation !== this.#waitingGeneration) return;
    try {
      const devices = await requestJson<{ devices: AndroidDeviceDto[] }>("/api/v1/devices");
      const saved = devices.devices.find(device => device.serial === profile.device.serial && device.ready !== false && (!device.state || device.state === "device"));
      if (saved) {
        this.cancelWaiting(false);
        try {
          // Re-enter the complete profile load path. This safely disconnects any
          // session the user may have opened while waiting before selecting the
          // exact saved serial and restoring the profile.
          await this.loadAndConnectProfile(profile, false);
        } catch (error) {
          this.setMainStatus("Profile connection failed", `${profile.name} · ${errorMessage(error)}`);
          this.setStatus(`Saved device appeared, but the profile connection failed: ${errorMessage(error)}`, true);
        }
        return;
      }
    } catch (error) {
      this.setStatus(`Waiting for ${profile.device.serial}; last device check failed: ${errorMessage(error)}`, true);
    }
    if (this.#waitingProfileId === profile.id && generation === this.#waitingGeneration) this.#waitingTimer = window.setTimeout(() => void this.pollWaitingProfile(profile, generation), 2000);
  }

  private cancelWaiting(userRequested: boolean): void {
    if (this.#waitingTimer !== null) window.clearTimeout(this.#waitingTimer);
    this.#waitingTimer = null; this.#waitingGeneration += 1; const wasWaiting = this.#waitingProfileId !== null; this.#waitingProfileId = null;
    const cancel = optionalElement<HTMLButtonElement>("connection-profile-cancel-wait"); if (cancel) cancel.hidden = true;
    if (userRequested && wasWaiting) { this.setMainStatus("Profile waiting cancelled", "No automatic profile connection is pending."); this.setStatus("Waiting for the saved profile device was cancelled."); }
    if (document.getElementById("connection-profile-select")) this.renderSelectionState();
  }

  private suggestedName(): string {
    const device = element<HTMLSelectElement>("device"); const deviceName = device.selectedOptions[0]?.textContent?.split(" · ")[0]?.trim() || "Android";
    const display = element<HTMLSelectElement>("display-mode").value === "virtual" ? element<HTMLSelectElement>("display-profile").selectedOptions[0]?.textContent?.trim() || "Virtual" : "Phone screen";
    return `${deviceName} – ${display}`.slice(0, 80);
  }

  private async saveCurrent(): Promise<void> {
    const name = window.prompt("Connection profile name", this.suggestedName())?.trim(); if (!name) return;
    const created = await requestJson<StoredConnectionProfile>("/api/v1/profiles", { method: "POST", body: JSON.stringify(await this.captureCurrent(name)) });
    await this.refreshProfiles(created.id); this.setStatus(`Saved connection profile: ${created.name}.`);
  }

  private async updateCurrent(): Promise<void> {
    const profile = this.selectedProfile(); if (!profile) throw new Error("Select a connection profile first.");
    const updated = await requestJson<StoredConnectionProfile>(`/api/v1/profiles/${encodeURIComponent(profile.id)}`, { method: "PUT", body: JSON.stringify(await this.captureCurrent(profile.name)) });
    await this.refreshProfiles(updated.id); this.setStatus(`Updated connection profile: ${updated.name}.`);
  }

  private async renameSelected(): Promise<void> {
    const profile = this.selectedProfile(); if (!profile) throw new Error("Select a connection profile first.");
    const name = window.prompt("Rename connection profile", profile.name)?.trim(); if (!name || name === profile.name) return;
    const input = profileInput(profile); input.name = name;
    const updated = await requestJson<StoredConnectionProfile>(`/api/v1/profiles/${encodeURIComponent(profile.id)}`, { method: "PUT", body: JSON.stringify(input) });
    await this.refreshProfiles(updated.id); this.setStatus(`Renamed connection profile to ${updated.name}.`);
  }

  private async deleteSelected(): Promise<void> {
    const profile = this.selectedProfile(); if (!profile) throw new Error("Select a connection profile first.");
    if (!window.confirm(`Delete connection profile “${profile.name}”?`)) return;
    if (this.#waitingProfileId === profile.id) this.cancelWaiting(false);
    await requestJson<Record<string, never>>(`/api/v1/profiles/${encodeURIComponent(profile.id)}`, { method: "DELETE" });
    await this.refreshProfiles(null); this.setStatus(`Deleted connection profile: ${profile.name}.`);
  }

  private async exportSelected(): Promise<void> {
    const profile = this.selectedProfile(); if (!profile) throw new Error("Select a connection profile first.");
    const safeName = profile.name.replace(/[^A-Za-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "") || "connection-profile";
    this.downloadJson(`DroidWebDisplay-${safeName}.json`, portableConnectionProfile(profile));
    this.setStatus(`Exported connection profile: ${profile.name}.`);
  }

  private async importSelectedFile(): Promise<void> {
    const input = element<HTMLInputElement>("connection-profile-file"); const file = input.files?.[0]; if (!file) return;
    try {
      const parsed = parsePortableConnectionProfile(JSON.parse(await file.text()));
      const names = new Set(this.#profiles.map(profile => profile.name.toLocaleLowerCase()));
      let name = parsed.name; let suffix = 2;
      while (names.has(name.toLocaleLowerCase())) name = `${parsed.name} (imported${suffix === 2 ? "" : ` ${suffix - 1}`})`.slice(0, 80), suffix += 1;
      const created = await requestJson<StoredConnectionProfile>("/api/v1/profiles", { method: "POST", body: JSON.stringify({ ...parsed, name }) });
      await this.refreshProfiles(created.id);
      this.setStatus(`Imported connection profile: ${created.name}. The saved device does not need to be attached until Load & Connect.`);
    } finally { input.value = ""; }
  }

  private downloadJson(filename: string, value: unknown): void {
    const blob = new Blob([`${JSON.stringify(value, null, 2)}\n`], { type: "application/json" }); const url = URL.createObjectURL(blob);
    try { const link = document.createElement("a"); link.href = url; link.download = filename; link.click(); } finally { URL.revokeObjectURL(url); }
  }

  private async changeDefault(): Promise<void> {
    const profile = this.selectedProfile(); const checked = element<HTMLInputElement>("connection-profile-default").checked; if (!profile) return;
    if (checked) { await requestJson(`/api/v1/profiles/${encodeURIComponent(profile.id)}/default`, { method: "PUT" }); this.#defaultProfileId = profile.id; }
    else { await requestJson("/api/v1/profiles/default", { method: "DELETE" }); this.#defaultProfileId = null; }
    this.renderSelectionState(); this.setStatus(checked ? `${profile.name} will auto-load at startup.` : "Startup profile disabled.");
  }

  private setMainStatus(title: string, details: string): void {
    const status = optionalElement<HTMLElement>("status"); const detail = optionalElement<HTMLElement>("details"); const container = optionalElement<HTMLElement>("connection-status");
    if (status) status.textContent = title; if (detail) detail.textContent = details; if (container) container.title = details;
  }

  private setStatus(text: string, error = false): void {
    const status = element<HTMLElement>("connection-profile-status"); status.textContent = text; status.classList.toggle("error-text", error);
  }

  private async run(action: () => Promise<void>): Promise<void> {
    try { await action(); }
    catch (error) { if (error instanceof ProfileDeviceUnavailableError) this.setMainStatus("Profile device unavailable", error.message); this.setStatus(errorMessage(error), true); }
  }
}
