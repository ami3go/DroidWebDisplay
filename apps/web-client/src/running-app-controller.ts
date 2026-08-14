import { BridgeApi } from "./api.js";
import type { RunningGuiAppDto, SessionDto } from "./types.js";

const DROPDOWN_REFRESH_STALE_MS = 1500;

interface Elements {
  readonly device: HTMLSelectElement;
  readonly select: HTMLSelectElement;
  readonly icon: HTMLButtonElement;
  readonly count: HTMLElement;
  readonly status: HTMLElement;
  readonly diagnosticDisplay: HTMLElement;
  readonly diagnosticRam: HTMLElement;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function formatBytes(value: number): string {
  const gib = value / (1024 ** 3);
  if (gib >= 1) return `${gib.toFixed(2)} GiB`;
  return `${(value / (1024 ** 2)).toFixed(0)} MiB`;
}

export class RunningAppController {
  readonly #api: BridgeApi;
  readonly #elements: Elements;
  #apps: readonly RunningGuiAppDto[] = [];
  #activeSession: SessionDto | null = null;
  #virtualSession: SessionDto | null = null;
  #refreshing = false;
  #moving = false;
  #timer: number | null = null;
  #lastRefreshAt = 0;
  #dropdownActive = false;
  #refreshAfterDropdown = false;
  #refreshQueued = false;

  public constructor(elements: Elements, api = new BridgeApi()) {
    this.#elements = elements;
    this.#api = api;
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
      if (this.#refreshing) this.#refreshQueued = true;
      else void this.refresh();
    });
  }

  public async initialize(): Promise<void> {
    await this.refresh();
    this.#timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void this.refresh(true);
    }, 4000);
  }

  public close(): void {
    if (this.#timer !== null) window.clearInterval(this.#timer);
    this.#timer = null;
  }

  public async refresh(silent = false): Promise<void> {
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
      this.#lastRefreshAt = 0;
      this.render();
      this.renderDiagnostics(null);
      this.#elements.status.textContent = "Select an authorized Android device.";
      return;
    }

    this.#refreshing = true;
    if (!silent) this.#elements.status.textContent = "Reading running Android applications…";
    try {
      const [apps, sessions] = await Promise.all([this.#api.runningApps(serial), this.#api.sessions()]);
      if (this.#elements.device.value !== serial) {
        this.#refreshQueued = true;
        return;
      }
      this.#apps = apps.apps;
      const runningSessions = sessions.sessions.filter(
        (session) => session.serial === serial && session.state === "running",
      );
      this.#virtualSession = runningSessions.find((session) =>
        session.displayMode === "virtual"
        && typeof session.virtualDisplay.displayId === "number"
      ) ?? null;
      this.#activeSession = this.#virtualSession ?? runningSessions[0] ?? null;
      this.#lastRefreshAt = Date.now();
      this.render();
      this.renderDiagnostics(apps.freeMemoryBytes ?? null);
      const displayId = this.#virtualSession?.virtualDisplay.displayId;
      this.#elements.status.textContent = displayId === null || displayId === undefined
        ? `${this.#apps.length} GUI task(s) found. Start a virtual display to move one.`
        : `${this.#apps.length} GUI task(s) found · target display ${displayId}.`;
      this.updateSelectionStatus();
    } catch (error) {
      this.#apps = [];
      this.#activeSession = null;
      this.#virtualSession = null;
      this.render();
      this.renderDiagnostics(null);
      this.#elements.status.textContent = `Running-app query failed: ${errorMessage(error)}`;
    } finally {
      this.#refreshing = false;
      if (this.#refreshQueued) {
        this.#refreshQueued = false;
        void this.refresh(true);
      }
    }
  }

  private beginDropdownInteraction(): void {
    this.#dropdownActive = true;
    if (Date.now() - this.#lastRefreshAt >= DROPDOWN_REFRESH_STALE_MS) {
      this.#refreshAfterDropdown = true;
    }
  }

  private async finishDropdownInteraction(): Promise<void> {
    this.#dropdownActive = false;
    if (!this.#refreshAfterDropdown) return;
    if (Date.now() - this.#lastRefreshAt < DROPDOWN_REFRESH_STALE_MS) {
      this.#refreshAfterDropdown = false;
      return;
    }
    if (this.#refreshing || this.#moving) return;
    this.#refreshAfterDropdown = false;
    await this.refresh(true);
  }

  private async handleSelectionChange(): Promise<void> {
    this.#dropdownActive = false;
    try {
      await this.moveSelected();
    } finally {
      await this.finishDropdownInteraction();
    }
  }

  private render(): void {
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

  private currentVirtualApp(): RunningGuiAppDto | null {
    const displayId = this.#virtualSession?.virtualDisplay.displayId ?? null;
    if (displayId === null) return null;
    return this.#apps.find((app) => app.displayId === displayId && app.resumed) ?? null;
  }

  private selectedApp(): RunningGuiAppDto | null {
    const taskId = Number(this.#elements.select.value);
    if (!Number.isInteger(taskId) || taskId <= 0) return null;
    return this.#apps.find((app) => app.taskId === taskId) ?? null;
  }

  private updateSelectionStatus(): void {
    const app = this.selectedApp();
    const displayId = this.#virtualSession?.virtualDisplay.displayId ?? null;
    if (!app) return;
    if (displayId === null) {
      this.#elements.status.textContent = "Start a virtual display to move the selected application.";
      return;
    }
    this.#elements.status.textContent = app.displayId === displayId
      ? `${app.label} is active on virtual display ${displayId}.`
      : `${app.label} is ready to move to virtual display ${displayId}.`;
  }

  private async moveSelected(): Promise<void> {
    if (this.#moving) return;
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
    } catch (error) {
      const message = `Move failed: ${errorMessage(error)}`;
      await this.refresh(true);
      this.#elements.status.textContent = message;
    } finally {
      this.#moving = false;
      this.#elements.select.disabled = this.#apps.length === 0;
      this.updateSelectionStatus();
    }
  }

  private renderDiagnostics(freeMemoryBytes: number | null): void {
    const displayId = this.#virtualSession?.virtualDisplay.displayId
      ?? (this.#activeSession?.displayMode === "physical" ? 0 : null);
    this.#elements.diagnosticDisplay.textContent = displayId === null ? "—" : String(displayId);
    this.#elements.diagnosticRam.textContent = freeMemoryBytes === null ? "—" : formatBytes(freeMemoryBytes);
  }
}
