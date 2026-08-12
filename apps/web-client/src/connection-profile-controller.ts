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
  reconnect: { enabled: boolean; attempts: number };
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
}

const PROFILE_INPUT_IDS = [
  "device",
  "display-mode",
  "display-profile",
  "virtual-size-mode",
  "virtual-width",
  "virtual-height",
  "virtual-dpi",
  "virtual-app-package",
  "virtual-force-stop",
  "virtual-keep-active",
  "virtual-system-decorations",
  "virtual-destroy-content",
  "virtual-ime-policy",
  "virtual-hide-keyboard",
  "virtual-preserve-aspect",
  "virtual-bitrate",
  "virtual-max-fps",
  "audio-enabled",
  "audio-volume",
  "clipboard-auto-sync",
  "clipboard-max-kib",
  "auto-reconnect",
  "reconnect-attempts",
  "latency-video-encoder",
] as const;

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

  public async initialize(): Promise<void> {
    if (this.#initialized) return;
    this.installUi();
    this.bindUi();
    this.bindDirtyTracking();
    await this.refreshProfiles();
    this.#initialized = true;
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
      <div class="two-button-row uniform-buttons">
        <button id="connection-profile-save" type="button" class="secondary">Save current</button>
        <button id="connection-profile-update" type="button" class="secondary" disabled>Update</button>
      </div>
      <div class="two-button-row uniform-buttons">
        <button id="connection-profile-rename" type="button" class="secondary" disabled>Rename</button>
        <button id="connection-profile-delete" type="button" class="danger" disabled>Delete</button>
      </div>
      <label class="toggle-row"><input id="connection-profile-default" type="checkbox" disabled> Auto-load this profile at startup</label>
      <p id="connection-profile-meta" class="running-app-status">No connection profile selected.</p>
      <p id="connection-profile-status" class="running-app-status">Profiles are stored by this DroidWebDisplay service.</p>
      <hr>`;
    card.prepend(panel);
  }

  private bindUi(): void {
    element<HTMLSelectElement>("connection-profile-select").addEventListener("change", () => this.selectProfile());
    element<HTMLButtonElement>("connection-profile-load").addEventListener("click", () => {
      this.setStatus("Load & Connect will be enabled by the restore engine in the next phase.");
    });
    element<HTMLButtonElement>("connection-profile-save").addEventListener("click", () => void this.run(() => this.saveCurrent()));
    element<HTMLButtonElement>("connection-profile-update").addEventListener("click", () => void this.run(() => this.updateCurrent()));
    element<HTMLButtonElement>("connection-profile-rename").addEventListener("click", () => void this.run(() => this.renameSelected()));
    element<HTMLButtonElement>("connection-profile-delete").addEventListener("click", () => void this.run(() => this.deleteSelected()));
    element<HTMLInputElement>("connection-profile-default").addEventListener("change", () => void this.run(() => this.changeDefault()));
  }

  private bindDirtyTracking(): void {
    for (const id of PROFILE_INPUT_IDS) {
      const target = document.getElementById(id);
      if (!target) continue;
      for (const eventName of ["input", "change"]) target.addEventListener(eventName, () => this.markDirty());
    }
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
    element<HTMLButtonElement>("connection-profile-load").disabled = !hasProfile;
    element<HTMLButtonElement>("connection-profile-update").disabled = !hasProfile || !this.#dirty;
    element<HTMLButtonElement>("connection-profile-rename").disabled = !hasProfile;
    element<HTMLButtonElement>("connection-profile-delete").disabled = !hasProfile;
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
    meta.textContent = `${profile.device.model ?? profile.device.serial} · ${profile.device.serial} · last used ${used}${defaultText}${this.#dirty ? " · modified" : ""}`;
  }

  private async currentDevice(): Promise<ConnectionProfileDevice> {
    const serial = element<HTMLSelectElement>("device").value;
    if (!serial) throw new Error("Select an authorized Android device before saving a connection profile.");
    const response = await requestJson<{ devices: AndroidDeviceDto[] }>("/api/v1/devices");
    const device = response.devices.find(item => item.serial === serial);
    return { serial, model: device?.model ?? null };
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
        width: Number(element<HTMLInputElement>("virtual-width").value),
        height: Number(element<HTMLInputElement>("virtual-height").value),
        dpi: Number(element<HTMLInputElement>("virtual-dpi").value),
        startApp: element<HTMLInputElement>("virtual-app-package").value.trim(),
        forceStopBeforeLaunch: element<HTMLInputElement>("virtual-force-stop").checked,
        keepActive: element<HTMLInputElement>("virtual-keep-active").checked,
        systemDecorations: element<HTMLInputElement>("virtual-system-decorations").checked,
        destroyContentOnClose: element<HTMLInputElement>("virtual-destroy-content").checked,
        imePolicy: hideKeyboard ? "hide" : (["local", "fallback"].includes(ime) ? ime as "local" | "fallback" : "default"),
        preserveAspectRatio: element<HTMLInputElement>("virtual-preserve-aspect").checked,
        videoBitRateMbps: Number(element<HTMLInputElement>("virtual-bitrate").value),
        maxFps: Number(element<HTMLInputElement>("virtual-max-fps").value),
      },
      audio: {
        enabled: element<HTMLInputElement>("audio-enabled").checked,
        muted: element<HTMLButtonElement>("audio-mute").textContent === "Unmute",
        volume: clamp(Number(element<HTMLInputElement>("audio-volume").value), 0, 100),
      },
      clipboard: {
        automatic: element<HTMLInputElement>("clipboard-auto-sync").checked,
        maximumKiB: clamp(Number(element<HTMLInputElement>("clipboard-max-kib").value), 1, 256),
      },
      reconnect: {
        enabled: element<HTMLInputElement>("auto-reconnect").checked,
        attempts: clamp(Number(element<HTMLSelectElement>("reconnect-attempts").value), 1, 20),
      },
      video: encoder ? { encoderMode: "selected", encoder } : { encoderMode: "auto", encoder: null },
    };
  }

  private suggestedName(): string {
    const device = element<HTMLSelectElement>("device");
    const deviceName = device.selectedOptions[0]?.textContent?.split(" · ")[0]?.trim() || "Android";
    const display = element<HTMLSelectElement>("display-mode").value === "virtual"
      ? element<HTMLSelectElement>("display-profile").selectedOptions[0]?.textContent?.trim() || "Virtual"
      : "Phone screen";
    return `${deviceName} – ${display}`.slice(0, 80);
  }

  private async saveCurrent(): Promise<void> {
    const name = window.prompt("Connection profile name", this.suggestedName())?.trim();
    if (!name) return;
    const created = await requestJson<StoredConnectionProfile>("/api/v1/profiles", {
      method: "POST",
      body: JSON.stringify(await this.captureCurrent(name)),
    });
    await this.refreshProfiles(created.id);
    this.setStatus(`Saved connection profile: ${created.name}.`);
  }

  private async updateCurrent(): Promise<void> {
    const profile = this.selectedProfile();
    if (!profile) throw new Error("Select a connection profile first.");
    const updated = await requestJson<StoredConnectionProfile>(`/api/v1/profiles/${encodeURIComponent(profile.id)}`, {
      method: "PUT",
      body: JSON.stringify(await this.captureCurrent(profile.name)),
    });
    await this.refreshProfiles(updated.id);
    this.setStatus(`Updated connection profile: ${updated.name}.`);
  }

  private async renameSelected(): Promise<void> {
    const profile = this.selectedProfile();
    if (!profile) throw new Error("Select a connection profile first.");
    const name = window.prompt("Rename connection profile", profile.name)?.trim();
    if (!name || name === profile.name) return;
    const input = profileInput(profile);
    input.name = name;
    const updated = await requestJson<StoredConnectionProfile>(`/api/v1/profiles/${encodeURIComponent(profile.id)}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
    await this.refreshProfiles(updated.id);
    this.setStatus(`Renamed connection profile to ${updated.name}.`);
  }

  private async deleteSelected(): Promise<void> {
    const profile = this.selectedProfile();
    if (!profile) throw new Error("Select a connection profile first.");
    if (!window.confirm(`Delete connection profile “${profile.name}”?`)) return;
    await requestJson<Record<string, never>>(`/api/v1/profiles/${encodeURIComponent(profile.id)}`, { method: "DELETE" });
    await this.refreshProfiles(null);
    this.setStatus(`Deleted connection profile: ${profile.name}.`);
  }

  private async changeDefault(): Promise<void> {
    const profile = this.selectedProfile();
    const checked = element<HTMLInputElement>("connection-profile-default").checked;
    if (!profile) return;
    if (checked) {
      await requestJson(`/api/v1/profiles/${encodeURIComponent(profile.id)}/default`, { method: "PUT" });
      this.#defaultProfileId = profile.id;
    } else {
      await requestJson("/api/v1/profiles/default", { method: "DELETE" });
      this.#defaultProfileId = null;
    }
    this.renderSelectionState();
    this.setStatus(checked ? `${profile.name} will auto-load at startup.` : "Startup profile disabled.");
  }

  private setStatus(text: string, error = false): void {
    const status = element<HTMLElement>("connection-profile-status");
    status.textContent = text;
    status.classList.toggle("error-text", error);
  }

  private async run(action: () => Promise<void>): Promise<void> {
    try {
      await action();
    } catch (error) {
      this.setStatus(errorMessage(error), true);
    }
  }
}
