import { BridgeApi } from "./api.js";
import type { AutoDownloadSnapshotDto, DuplicatePolicy } from "./types.js";

interface AutoDownloadElements {
  readonly device: HTMLSelectElement;
  readonly enabled: HTMLInputElement;
  readonly pcToAndroidEnabled: HTMLInputElement;
  readonly source: HTMLSelectElement;
  readonly destination: HTMLSelectElement;
  readonly uploadDuplicatePolicy: HTMLSelectElement;
  readonly scanInterval: HTMLInputElement;
  readonly stabilitySeconds: HTMLInputElement;
  readonly stabilityObservations: HTMLInputElement;
  readonly includeExisting: HTMLInputElement;
  readonly includeExistingPc: HTMLInputElement;
  readonly deleteAfterVerified: HTMLInputElement;
  readonly notifications: HTMLInputElement;
  readonly save: HTMLButtonElement;
  readonly scanNow: HTMLButtonElement;
  readonly reset: HTMLButtonElement;
  readonly status: HTMLElement;
  readonly summary: HTMLElement;
  readonly events: HTMLElement;
}

export class AutoDownloadController {
  readonly #api = new BridgeApi();
  #timer: number | null = null;
  #snapshot: AutoDownloadSnapshotDto | null = null;
  #refreshing = false;
  #lastNotificationTimestamp = Number(localStorage.getItem("droidwebdisplay-auto-download-notification-ts") ?? "0");

  public constructor(private readonly elements: AutoDownloadElements) {
    this.bindEvents();
  }

  public async initialize(): Promise<void> {
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
    this.scheduleRefresh();
    document.addEventListener("visibilitychange", () => this.scheduleRefresh(0));
    document.querySelector<HTMLButtonElement>('[data-group="files"]')?.addEventListener("click", () => this.scheduleRefresh(0));
  }

  private bindEvents(): void {
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

  private async refreshRoots(): Promise<void> {
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

  private async save(): Promise<void> {
    const serial = this.elements.device.value || null;
    await this.#api.configureAutoDownload({
      enabled: this.elements.enabled.checked,
      pcToAndroidEnabled: this.elements.pcToAndroidEnabled.checked,
      serial,
      sourcePath: this.elements.source.value || "/sdcard/Download",
      destinationProfile: this.elements.destination.value || "default-downloads",
      duplicatePolicy: "rename" as DuplicatePolicy,
      uploadDuplicatePolicy: this.elements.uploadDuplicatePolicy.value as DuplicatePolicy,
      scanIntervalSeconds: numberValue(this.elements.scanInterval, 2),
      stabilitySeconds: numberValue(this.elements.stabilitySeconds, 3),
      stabilityObservations: numberValue(this.elements.stabilityObservations, 3),
      includeExisting: this.elements.includeExisting.checked,
      includeExistingPc: this.elements.includeExistingPc.checked,
      deleteAfterVerified: this.elements.deleteAfterVerified.checked,
    });
    this.applySnapshot(await this.#api.scanAutoDownload());
  }

  private filesDrawerVisible(): boolean {
    return document.visibilityState === "visible"
      && document.querySelector('.gb-drawer')?.classList.contains("gb-open") === true
      && document.querySelector('.gb-drawer-slot[data-slot="files"]')?.classList.contains("gb-active") === true;
  }

  private refreshDelay(): number {
    if (document.visibilityState !== "visible") return 10_000;
    if (this.filesDrawerVisible()) return 1500;
    const monitoring = Boolean(this.#snapshot?.config.enabled || this.#snapshot?.config.pcToAndroidEnabled);
    return monitoring ? 5000 : 10_000;
  }

  private scheduleRefresh(delay = this.refreshDelay()): void {
    if (this.#timer !== null) window.clearTimeout(this.#timer);
    this.#timer = window.setTimeout(() => {
      this.#timer = null;
      void this.refresh().finally(() => this.scheduleRefresh());
    }, Math.max(0, delay));
  }

  private async refresh(): Promise<void> {
    if (this.#refreshing) return;
    this.#refreshing = true;
    try {
      this.applySnapshot(await this.#api.autoDownload());
    } catch (error) {
      this.elements.status.textContent = "Unavailable";
      this.elements.summary.textContent = errorMessage(error);
      this.elements.summary.classList.add("error-text");
    } finally {
      this.#refreshing = false;
    }
  }

  private applySnapshot(snapshot: AutoDownloadSnapshotDto, initialize = false): void {
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
      this.elements.notifications.checked = localStorage.getItem("droidwebdisplay-auto-download-notifications") === "true";
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

  private renderEvents(snapshot: AutoDownloadSnapshotDto): void {
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

  private async configureNotifications(): Promise<void> {
    localStorage.setItem("droidwebdisplay-auto-download-notifications", String(this.elements.notifications.checked));
    if (!this.elements.notifications.checked || !("Notification" in globalThis)) return;
    if (Notification.permission === "default") await Notification.requestPermission();
    if (Notification.permission !== "granted") this.elements.notifications.checked = false;
    localStorage.setItem("droidwebdisplay-auto-download-notifications", String(this.elements.notifications.checked));
  }

  private notifyNewEvents(snapshot: AutoDownloadSnapshotDto): void {
    const notifications = snapshot.runtime.notifications.filter((item) => item.timestamp > this.#lastNotificationTimestamp);
    if (!notifications.length) return;
    this.#lastNotificationTimestamp = Math.max(...notifications.map((item) => item.timestamp));
    localStorage.setItem("droidwebdisplay-auto-download-notification-ts", String(this.#lastNotificationTimestamp));
    if (!this.elements.notifications.checked || !("Notification" in globalThis) || Notification.permission !== "granted") return;
    for (const item of notifications) {
      if (!["download-completed", "upload-completed", "monitor-error", "download-failed", "upload-failed"].includes(item.event)) continue;
      new Notification("DroidWebDisplay", { body: item.message, tag: `droidwebdisplay-${item.event}-${item.transferId ?? item.timestamp}` });
    }
  }

  private async runAction(action: () => Promise<void>): Promise<void> {
    try {
      await action();
    } catch (error) {
      this.elements.status.textContent = "Error";
      this.elements.status.classList.add("error-text");
      this.elements.summary.textContent = errorMessage(error);
      this.elements.summary.classList.add("error-text");
    }
  }
}

function numberValue(input: HTMLInputElement, fallback: number): number {
  const value = Number(input.value);
  return Number.isFinite(value) ? value : fallback;
}

function setSelectValue(select: HTMLSelectElement, value: string): void {
  if ([...select.options].some((option) => option.value === value)) select.value = value;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
