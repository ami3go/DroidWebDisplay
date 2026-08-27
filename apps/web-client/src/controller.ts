import {
  ControlMessageType,
  DeviceMessageType,
  ScrcpyV41Adapter,
  type ControlMessage,
  type ScrcpyV41Session,
} from "@droid-web-display/scrcpy-protocol";
import { BridgeApi, type StartSessionRequest } from "./api.js";
import { CLIPBOARD_STATUS } from "./clipboard-status.js";
import { ManualCopyDuplicateGuard } from "./clipboard-events.js";
import {
  alignedFlexSize,
  buildSessionRequest,
  validateDisplayForm,
  VIRTUAL_DISPLAY_PROFILES,
  type DisplayFormValues,
} from "./display-config.js";
import { androidClipboardCopyMessage, androidKeyPress, clipboardMessage, clipboardShortcut, isEditableTarget, keyboardMessages, mapClientPoint, textInjectionMessages } from "./input.js";
import {
  MAX_QUICK_APP_BUTTONS,
  moveQuickApp,
  nextQuickAppPackage,
  normalizeQuickAppPackages,
  normalizeQuickAppsByDevice,
  type QuickAppsByDevice,
} from "./quick-apps.js";
import type { AndroidDevice, LaunchableAppDto, SessionDto, VirtualDisplayCapabilities } from "./types.js";
import { WebCodecsVideoRenderer, type VideoStatistics } from "./video-renderer.js";
import { WebSocketBridgeTransport } from "./websocket-transport.js";
import { WebCodecsAudioPlayer, type AudioStatistics } from "./audio-player.js";

const DEVICE_DROPDOWN_REFRESH_STALE_MS = 1500;
// textInjectionMessages chunks at 300 UTF-8 bytes and sendMessages awaits every
// chunk, so injection cost grows linearly with the text: ~875 sequential round
// trips at the 256 KiB clipboard limit. Above this size the clipboard is still
// synchronized and the user pastes on the device.
const MAX_INJECTED_BYTES = 8 * 1024;
// An unacknowledged automatic sync is deliberately retryable, but the poller
// runs every 1800ms and only skips text it has recorded as sent, so without a
// cap the same text is re-sent every tick for as long as it stays on the PC
// clipboard. Give up after this many attempts and stop asking.
const MAX_UNACKNOWLEDGED_SYNC_ATTEMPTS = 3;

interface ClipboardAckWaiter {
  readonly resolve: (acknowledged: boolean) => void;
  readonly timer: number;
}

interface Elements {
  readonly device: HTMLSelectElement;
  readonly connect: HTMLButtonElement;
  readonly canvas: HTMLCanvasElement;
  readonly stage: HTMLElement;
  readonly statusContainer: HTMLElement;
  readonly statusIcon: HTMLElement;
  readonly status: HTMLElement;
  readonly details: HTMLElement;
  readonly statistics: HTMLElement;
  readonly back: HTMLButtonElement;
  readonly home: HTMLButtonElement;
  readonly recent: HTMLButtonElement;
  readonly rotate: HTMLButtonElement;
  readonly power: HTMLButtonElement;
  readonly clipboard: HTMLButtonElement;
  readonly clipboardText: HTMLTextAreaElement;
  readonly clipboardTextPaste: HTMLButtonElement;
  readonly fullscreen: HTMLButtonElement;
  readonly audioEnabled: HTMLInputElement;
  readonly audioMute: HTMLButtonElement;
  readonly audioVolume: HTMLInputElement;
  readonly audioStatus: HTMLElement;
  readonly autoReconnect: HTMLInputElement;
  readonly reconnectAttempts: HTMLSelectElement;
  readonly reconnect: HTMLButtonElement;
  readonly sessionChannels: HTMLElement;
  readonly clipboardAutoSync: HTMLInputElement;
  readonly clipboardMaxKib: HTMLInputElement;
  readonly clipboardCopyAndroid: HTMLButtonElement;
  readonly settingsExport: HTMLButtonElement;
  readonly settingsImport: HTMLButtonElement;
  readonly settingsFile: HTMLInputElement;
  readonly settingsStatus: HTMLElement;
  readonly quickAppHeader: HTMLElement;
  readonly quickAppAdd: HTMLButtonElement;
  readonly quickAppList: HTMLElement;
  readonly quickAppSettingsStatus: HTMLElement;
  readonly displayMode: HTMLSelectElement;
  readonly displayProfile: HTMLSelectElement;
  readonly virtualSettings: HTMLElement;
  readonly sizeMode: HTMLSelectElement;
  readonly virtualWidth: HTMLInputElement;
  readonly virtualHeight: HTMLInputElement;
  readonly virtualDpi: HTMLInputElement;
  readonly virtualApp: HTMLSelectElement;
  readonly manualApp: HTMLInputElement;
  readonly forceStop: HTMLInputElement;
  readonly keepActive: HTMLInputElement;
  readonly systemDecorations: HTMLInputElement;
  readonly destroyContent: HTMLInputElement;
  readonly imePolicy: HTMLSelectElement;
  readonly hideVirtualKeyboard: HTMLInputElement;
  readonly preserveAspect: HTMLInputElement;
  readonly videoBitrate: HTMLInputElement;
  readonly virtualMaxFps: HTMLInputElement;
  readonly displaySummary: HTMLElement;
  readonly capability: HTMLElement;
}

export class DroidWebDisplayController {
  readonly #api = new BridgeApi();
  readonly #adapter = new ScrcpyV41Adapter();
  #transport: WebSocketBridgeTransport | null = null;
  #protocolSession: ScrcpyV41Session | null = null;
  #serverSession: SessionDto | null = null;
  #renderer: WebCodecsVideoRenderer;
  #audioPlayer: WebCodecsAudioPlayer;
  #latestAudioStatistics: AudioStatistics | null = null;
  #audioTask: Promise<void> | null = null;
  #clipboardSequence = 1n;
  #powerOn = true;
  #closing = false;
  #manualDisconnect = false;
  #reconnectTimer: number | null = null;
  #reconnectCount = 0;
  #lastConnectValues: DisplayFormValues | null = null;
  #lastAndroidClipboard = "";
  #lastSentClipboard = "";
  #unacknowledgedSync: { readonly text: string; readonly attempts: number } | null = null;
  #clipboardPollTimer: number | null = null;
  #clipboardReadAllowed = false;
  #clipboardPollBusy = false;
  #copyShortcutPending = false;
  #copyShortcutTimer: number | null = null;
  #latestStatistics: VideoStatistics | null = null;
  #deviceMessageTask: Promise<void> | null = null;
  #capabilities: VirtualDisplayCapabilities | null = null;
  #capabilityRequestGeneration = 0;
  #launchableApps: readonly LaunchableAppDto[] = [];
  #launchableAppsLoaded = false;
  #launchableAppsError: string | null = null;
  #quickAppsByDevice: QuickAppsByDevice = {};
  #quickAppLaunching: string | null = null;
  #deviceListRefreshedAt = 0;
  #resizeObserver: ResizeObserver | null = null;
  #resizeTimer: number | null = null;
  #lastResizeAt = 0;
  #lastRequestedSize: { width: number; height: number } | null = null;
  readonly #clipboardAcks = new Map<bigint, ClipboardAckWaiter>();
  readonly #manualCopyDuplicate = new ManualCopyDuplicateGuard();

  public constructor(private readonly elements: Elements) {
    this.#renderer = new WebCodecsVideoRenderer(elements.canvas, (stats) => this.updateStatistics(stats));
    this.#audioPlayer = new WebCodecsAudioPlayer((stats) => this.updateAudioStatistics(stats));
    this.populateProfiles();
    this.updatePowerButton();
    this.bindEvents();
  }

  public async initialize(): Promise<void> {
    this.applyProfile(localStorage.getItem("droidwebdisplay-virtual-profile-v1") ?? "chatgpt-desktop");
    this.restoreBrowserSettings();
    this.updateClipboardUi();
    this.renderQuickApps();
    await this.refreshDevices();
    await this.refreshVirtualCapabilities();
    this.updateDisplayUi();
    this.setStatus("Ready", "Select an authorized Android device and connect.");
  }

  public async refreshDevices(): Promise<void> {
    const response = await this.#api.devices();
    const previous = this.elements.device.value;
    this.elements.device.replaceChildren();
    for (const device of response.devices) {
      const option = document.createElement("option");
      option.value = device.serial;
      option.textContent = deviceLabel(device);
      option.disabled = !device.ready;
      this.elements.device.append(option);
    }
    const readyOptions = [...this.elements.device.options].filter((option) => !option.disabled);
    const previousOption = readyOptions.find((option) => option.value === previous);
    if (previousOption) previousOption.selected = true;
    else if (readyOptions.length === 1) readyOptions[0]!.selected = true;
    this.#deviceListRefreshedAt = Date.now();
    this.updateConnectAvailability();
  }

  public async connect(): Promise<void> {
    if (this.#serverSession) return;
    const serial = this.elements.device.value;
    if (!serial) throw new Error("No authorized device is selected");
    const values = this.readDisplayValues();
    this.#lastConnectValues = values;
    const errors = validateDisplayForm(values);
    if (errors.length) throw new Error(errors.join(" "));
    if (values.displayMode === "virtual" && !this.#capabilities?.virtualDisplaySupported) {
      throw new Error(this.#capabilities?.warnings.join(" ") || "Virtual Display mode is not supported by this device.");
    }

    this.setBusy(true);
    this.setStatus(
      "Starting",
      values.displayMode === "virtual" ? "Creating Android virtual display and opening browser channels…" : "Launching scrcpy and opening browser channels…",
    );
    try {
      const request = { ...buildSessionRequest(values, serial), audio: this.elements.audioEnabled.checked, audioCodec: "opus", audioBitRate: 128_000 } as StartSessionRequest;
      const serverSession = await this.#api.startSession(request);
      this.#serverSession = serverSession;
      this.#transport = new WebSocketBridgeTransport(serverSession.sessionId);
      this.#protocolSession = await this.#adapter.connect(this.#transport, {
        video: true,
        audio: this.elements.audioEnabled.checked,
        control: true,
      });
      this.resetClipboardSessionState();
      this.setConnectedControls(true);
      this.elements.canvas.focus();
      this.#deviceMessageTask = this.consumeDeviceMessages(this.#protocolSession);
      void this.#deviceMessageTask.catch((error: unknown) => {
        if (!this.#closing && this.#serverSession) console.warn("Control device-message stream ended", error);
      });
      void this.#renderer.run(this.#protocolSession).catch((error: unknown) => this.handleStreamFailure(error));
      if (this.elements.audioEnabled.checked) {
        if (this.#protocolSession.audioHeader) {
          this.#audioPlayer.setMuted(this.elements.audioMute.textContent === "Unmute");
          this.#audioPlayer.setVolume(Number(this.elements.audioVolume.value) / 100);
          this.elements.audioStatus.textContent = `Audio connected · ${this.#protocolSession.audioHeader.codec}`;
          this.#audioTask = this.#audioPlayer.run(this.#protocolSession);
          void this.#audioTask.catch((error: unknown) => {
            if (this.#serverSession) this.elements.audioStatus.textContent = `Audio unavailable: ${errorMessage(error)}. Video and control remain active.`;
          });
        } else {
          this.elements.audioStatus.textContent = "Android audio capture is unavailable. Video and control remain active.";
        }
      } else {
        this.elements.audioStatus.textContent = "Audio disabled.";
      }
      void this.startClipboardPolling(false);
      this.#reconnectCount = 0;

      if (values.displayMode === "virtual") {
        if (values.startApp) {
          const payload = values.forceStopBeforeLaunch ? `+${values.startApp}` : values.startApp;
          await this.sendMessages([{ type: ControlMessageType.StartApp, name: payload }]);
          await this.#api.recordApplicationLaunch(serverSession.sessionId, "sent");
        }
        if (values.sizeMode === "flex") this.startFlexResize(values);
        const display = serverSession.virtualDisplay;
        this.setStatus(
          "Virtual display connected",
          `Display ${display.displayId ?? "pending"} · ${display.actualSize ?? `${values.width}x${values.height}`} · ${display.actualDpi ?? values.dpi} DPI`,
        );
      } else {
        const deviceName = this.#protocolSession.device?.name ?? serverSession.serial;
        this.setStatus("Connected", `${deviceName} · H.264 · ${serverSession.options.maxFps} fps limit`);
      }
    } catch (error) {
      await this.cleanupSession();
      this.setStatus("Connection failed", errorMessage(error));
      this.setConnectedControls(false);
      throw error;
    } finally {
      this.setBusy(false);
    }
  }

  public async disconnect(): Promise<void> {
    this.#manualDisconnect = true;
    this.cancelReconnect();
    this.#closing = true;
    try {
      await this.cleanupSession();
      this.setStatus("Disconnected", "The Android session was stopped and virtual-display cleanup was requested.");
    } finally {
      this.#closing = false;
      this.setConnectedControls(false);
      this.#manualDisconnect = false;
    }
  }

  public stopOnUnload(): void {
    const sessionId = this.#serverSession?.sessionId;
    if (!sessionId) return;
    void this.#api.stopSession(sessionId, true);
  }

  private bindEvents(): void {
    this.elements.device.addEventListener("pointerdown", () => void this.runUiAction(() => this.refreshDevicesIfStale()));
    this.elements.device.addEventListener("focus", () => void this.runUiAction(() => this.refreshDevicesIfStale()));
    this.elements.device.addEventListener("change", () => {
      this.#launchableApps = [];
      this.#launchableAppsLoaded = false;
      this.#launchableAppsError = null;
      this.renderQuickApps();
      void this.runUiAction(() => this.refreshVirtualCapabilities());
    });
    this.elements.connect.addEventListener("click", () => void this.runUiAction(() => this.#serverSession ? this.disconnect() : this.connect()));
    this.elements.displayMode.addEventListener("change", () => this.updateDisplayUi());
    this.elements.displayProfile.addEventListener("change", () => {
      if (this.elements.displayProfile.value !== "custom") this.applyProfile(this.elements.displayProfile.value);
      this.updateDisplayUi();
    });
    for (const element of this.displayInputs()) {
      element.addEventListener("input", () => this.onCustomDisplayChange());
      element.addEventListener("change", () => this.onCustomDisplayChange());
    }
    this.elements.virtualApp.addEventListener("change", () => {
      this.elements.manualApp.value = this.elements.virtualApp.value;
      this.onCustomDisplayChange();
    });
    this.elements.back.addEventListener("click", () => void this.sendMessages([
      { type: ControlMessageType.BackOrScreenOn, action: 0 },
      { type: ControlMessageType.BackOrScreenOn, action: 1 },
    ]));
    this.elements.home.addEventListener("click", () => void this.sendMessages(androidKeyPress(3)));
    this.elements.recent.addEventListener("click", () => void this.sendMessages(androidKeyPress(187)));
    this.elements.rotate.addEventListener("click", () => void this.rotate());
    this.elements.power.addEventListener("click", () => void this.togglePower());
    this.elements.clipboard.addEventListener("click", () => void this.runUiAction(() => this.pasteClipboard()));
    this.elements.clipboardTextPaste.addEventListener("click", () => void this.runUiAction(() => this.pasteTypedText()));
    this.elements.clipboardText.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); void this.runUiAction(() => this.pasteTypedText()); } });
    this.elements.fullscreen.addEventListener("click", () => void this.toggleFullscreen());
    this.elements.audioMute.addEventListener("click", () => this.toggleAudioMute());
    this.elements.audioVolume.addEventListener("input", () => this.setAudioVolume());
    this.elements.audioEnabled.addEventListener("change", () => this.saveBrowserSettings());
    this.elements.autoReconnect.addEventListener("change", () => this.saveBrowserSettings());
    this.elements.reconnectAttempts.addEventListener("change", () => this.saveBrowserSettings());
    this.elements.reconnect.addEventListener("click", () => void this.runUiAction(() => this.reconnectNow()));
    this.elements.clipboardAutoSync.addEventListener("change", () => void this.runUiAction(async () => {
      this.saveBrowserSettings();
      this.updateClipboardUi();
      await this.startClipboardPolling(true);
    }));
    this.elements.clipboardMaxKib.addEventListener("change", () => this.saveBrowserSettings());
    this.elements.clipboardCopyAndroid.addEventListener("click", () => void this.runUiAction(() => this.copyAndroidClipboard()));
    this.elements.settingsExport.addEventListener("click", () => this.exportSettings());
    this.elements.settingsImport.addEventListener("click", () => this.elements.settingsFile.click());
    this.elements.settingsFile.addEventListener("change", () => void this.runUiAction(() => this.importSettings()));
    this.elements.quickAppAdd.addEventListener("click", () => this.addQuickApp());
    this.elements.quickAppHeader.addEventListener("click", (event) => void this.runUiAction(() => this.handleQuickAppHeaderClick(event)));
    this.elements.quickAppList.addEventListener("change", (event) => this.handleQuickAppSelection(event));
    this.elements.quickAppList.addEventListener("click", (event) => this.handleQuickAppAction(event));
    this.elements.canvas.addEventListener("contextmenu", (event) => event.preventDefault());
    this.elements.canvas.addEventListener("pointerdown", (event) => void this.pointer(event, 0));
    this.elements.canvas.addEventListener("pointermove", (event) => {
      if (event.buttons !== 0) void this.pointer(event, 2);
    });
    this.elements.canvas.addEventListener("pointerup", (event) => void this.pointer(event, 1));
    this.elements.canvas.addEventListener("pointercancel", (event) => void this.pointer(event, 3));
    this.elements.canvas.addEventListener("wheel", (event) => void this.scroll(event), { passive: false });
    document.addEventListener("keydown", (event) => {
      if (event.key === "F11") { event.preventDefault(); void this.toggleFullscreen(); return; }
      const selection = document.getSelection();
      if (
        !this.#protocolSession
        || event.repeat
        || isEditableTarget(event.target)
        || (selection !== null && !selection.isCollapsed)
        || clipboardShortcut(event) !== "copy"
      ) return;
      event.preventDefault();
      void this.runUiAction(async () => {
        this.beginAndroidCopyRequest("Ctrl+C");
        await this.sendMessages([androidClipboardCopyMessage()]);
      });
    });
    this.elements.canvas.addEventListener("keydown", (event) => void this.keydown(event));
    // Ctrl+V is routed from the native paste event rather than from keydown, so
    // ClipboardEvent.clipboardData can be read without Async Clipboard
    // permission. The listener has to be on the document because paste fires
    // on whichever element currently owns focus. Drawer controls can move focus
    // away from the canvas, so a canvas-only listener would make Ctrl+V die.
    document.addEventListener("paste", (event) => {
      if (!this.#protocolSession || isEditableTarget(event.target)) return;
      const text = event.clipboardData?.getData("text/plain") ?? "";
      if (!text) return;
      event.preventDefault();
      void this.runUiAction(() => this.pasteText(text, "Ctrl+V"));
    });
  }

  private updateClipboardUi(): void { document.querySelector<HTMLElement>("#clipboard-card")?.classList.toggle("auto-sync-enabled", this.elements.clipboardAutoSync.checked); }

  private populateProfiles(): void {
    this.elements.displayProfile.replaceChildren();
    for (const profile of Object.values(VIRTUAL_DISPLAY_PROFILES)) {
      const option = document.createElement("option");
      option.value = profile.profileId;
      option.textContent = profile.label;
      this.elements.displayProfile.append(option);
    }
    const custom = document.createElement("option");
    custom.value = "custom";
    custom.textContent = "Custom";
    this.elements.displayProfile.append(custom);
  }

  private applyProfile(profileId: string): void {
    const profile = VIRTUAL_DISPLAY_PROFILES[profileId] ?? VIRTUAL_DISPLAY_PROFILES["chatgpt-desktop"]!;
    this.elements.displayProfile.value = profile.profileId;
    this.elements.sizeMode.value = profile.sizeMode;
    this.elements.virtualWidth.value = String(profile.width);
    this.elements.virtualHeight.value = String(profile.height);
    this.elements.virtualDpi.value = String(profile.dpi);
    this.elements.manualApp.value = profile.startApp;
    this.elements.forceStop.checked = profile.forceStopBeforeLaunch;
    this.elements.keepActive.checked = profile.keepActive;
    this.elements.systemDecorations.checked = profile.systemDecorations;
    this.elements.destroyContent.checked = profile.destroyContentOnClose;
    this.elements.hideVirtualKeyboard.checked = profile.imePolicy === "hide";
    this.elements.imePolicy.value = profile.imePolicy === "hide" ? "default" : profile.imePolicy;
    this.elements.preserveAspect.checked = profile.preserveAspectRatio;
    this.elements.videoBitrate.value = String(profile.videoBitRate / 1_000_000);
    this.elements.virtualMaxFps.value = String(profile.maxFps);
    localStorage.setItem("droidwebdisplay-virtual-profile-v1", profile.profileId);
  }

  private onCustomDisplayChange(): void {
    if (this.elements.displayMode.value === "virtual") this.elements.displayProfile.value = "custom";
    this.updateDisplayUi();
  }

  private displayInputs(): readonly (HTMLInputElement | HTMLSelectElement)[] {
    return [
      this.elements.sizeMode,
      this.elements.virtualWidth,
      this.elements.virtualHeight,
      this.elements.virtualDpi,
      this.elements.manualApp,
      this.elements.forceStop,
      this.elements.keepActive,
      this.elements.systemDecorations,
      this.elements.destroyContent,
      this.elements.imePolicy,
      this.elements.hideVirtualKeyboard,
      this.elements.preserveAspect,
      this.elements.videoBitrate,
      this.elements.virtualMaxFps,
    ];
  }

  private readDisplayValues(): DisplayFormValues {
    return {
      displayMode: this.elements.displayMode.value as DisplayFormValues["displayMode"],
      profileId: this.elements.displayProfile.value,
      sizeMode: this.elements.sizeMode.value as DisplayFormValues["sizeMode"],
      width: Number(this.elements.virtualWidth.value),
      height: Number(this.elements.virtualHeight.value),
      dpi: Number(this.elements.virtualDpi.value),
      startApp: this.elements.manualApp.value.trim(),
      forceStopBeforeLaunch: this.elements.forceStop.checked,
      keepActive: this.elements.keepActive.checked,
      systemDecorations: this.elements.systemDecorations.checked,
      destroyContentOnClose: this.elements.destroyContent.checked,
      imePolicy: this.elements.hideVirtualKeyboard.checked ? "hide" : this.elements.imePolicy.value as DisplayFormValues["imePolicy"],
      preserveAspectRatio: this.elements.preserveAspect.checked,
      videoBitRateMbps: Number(this.elements.videoBitrate.value),
      maxFps: Number(this.elements.virtualMaxFps.value),
    };
  }

  private updateDisplayUi(): void {
    const virtual = this.elements.displayMode.value === "virtual";
    this.elements.virtualSettings.hidden = !virtual;
    this.elements.imePolicy.disabled = Boolean(this.#protocolSession) || this.elements.hideVirtualKeyboard.checked;
    const values = this.readDisplayValues();
    const errors = validateDisplayForm(values);
    const aspect = values.height > 0 ? (values.width / values.height).toFixed(3) : "—";
    const megapixels = values.width > 0 && values.height > 0 ? ((values.width * values.height) / 1_000_000).toFixed(2) : "—";
    const warning = values.width * values.height > 1920 * 1080 || values.videoBitRateMbps > 20 ? " · High-load configuration" : "";
    this.elements.displaySummary.textContent = virtual
      ? errors.length ? errors.join(" ") : `${values.width}×${values.height} · ${values.dpi} DPI · AR ${aspect} · ${megapixels} MP${warning}`
      : "Mirrors Android display 0. This remains the default compatibility mode.";
    this.elements.displaySummary.classList.toggle("error-text", errors.length > 0);
    this.updateConnectAvailability();
  }

  private updateConnectAvailability(): void {
    if (this.#serverSession) {
      this.elements.connect.disabled = false;
      return;
    }
    const hasDevice = [...this.elements.device.options].some((option) => !option.disabled);
    const errors = validateDisplayForm(this.readDisplayValues());
    const unsupported = this.elements.displayMode.value === "virtual" && this.#capabilities?.virtualDisplaySupported === false;
    this.elements.connect.disabled = !hasDevice || this.#serverSession !== null || errors.length > 0 || unsupported;
  }

  private async refreshDevicesIfStale(): Promise<void> {
    if (Date.now() - this.#deviceListRefreshedAt < DEVICE_DROPDOWN_REFRESH_STALE_MS) return;
    const selected = this.elements.device.value;
    await this.refreshDevices();
    if (this.elements.device.value !== selected) await this.refreshVirtualCapabilities();
  }

  private async refreshVirtualCapabilities(): Promise<void> {
    const generation = ++this.#capabilityRequestGeneration;
    const serial = this.elements.device.value;
    if (!serial) {
      this.#capabilities = null;
      this.#launchableApps = [];
      this.#launchableAppsLoaded = false;
      this.#launchableAppsError = null;
      this.elements.capability.textContent = "Select an authorized device to probe virtual-display support.";
      this.renderQuickApps();
      return;
    }
    const [capabilityResult, appsResult] = await Promise.allSettled([
      this.#api.virtualDisplayCapabilities(serial, this.elements.manualApp.value.trim() || "com.openai.chatgpt"),
      this.#api.launchableApps(serial),
    ]);
    if (generation !== this.#capabilityRequestGeneration || this.elements.device.value !== serial) return;

    this.#launchableAppsLoaded = true;
    if (appsResult.status === "fulfilled") {
      this.#launchableApps = appsResult.value.apps;
      this.#launchableAppsError = null;
      const previous = this.elements.virtualApp.value;
      this.elements.virtualApp.replaceChildren();
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "Manual package / no app";
      this.elements.virtualApp.append(empty);
      for (const app of this.#launchableApps) {
        const option = document.createElement("option");
        option.value = app.packageName;
        option.textContent = `${app.label} · ${app.packageName}`;
        this.elements.virtualApp.append(option);
      }
      const desired = previous || this.elements.manualApp.value;
      if ([...this.elements.virtualApp.options].some((option) => option.value === desired)) this.elements.virtualApp.value = desired;
    } else {
      this.#launchableApps = [];
      this.#launchableAppsError = errorMessage(appsResult.reason);
    }
    this.renderQuickApps();

    if (capabilityResult.status === "fulfilled") {
      const capabilities = capabilityResult.value;
      this.#capabilities = capabilities;
      const localImeOption = [...this.elements.imePolicy.options].find((option) => option.value === "local");
      if (localImeOption) localImeOption.disabled = !capabilities.localImePolicySupported;
      if (!capabilities.localImePolicySupported && this.elements.imePolicy.value === "local") {
        this.elements.imePolicy.value = "default";
      }
      const warningText = capabilities.warnings.length ? ` · ${capabilities.warnings.join(" ")}` : "";
      this.elements.capability.textContent = capabilities.virtualDisplaySupported
        ? `Supported · API ${capabilities.deviceApi} · codecs ${capabilities.supportedCodecs.join(", ")} · secondary-display input available${warningText}`
        : capabilities.warnings.join(" ");
      this.elements.capability.classList.toggle("error-text", !capabilities.virtualDisplaySupported);
    } else {
      this.#capabilities = null;
      this.elements.capability.textContent = `Capability probe failed: ${errorMessage(capabilityResult.reason)}. Physical Screen mode remains available.`;
      this.elements.capability.classList.add("error-text");
    }
    this.updateConnectAvailability();
  }

  private currentQuickAppPackages(): readonly string[] {
    const serial = this.elements.device.value;
    return serial ? this.#quickAppsByDevice[serial] ?? [] : [];
  }

  private setCurrentQuickAppPackages(value: readonly string[]): void {
    const serial = this.elements.device.value;
    if (!serial) return;
    const packages = normalizeQuickAppPackages(value);
    const byDevice: Record<string, readonly string[]> = { ...this.#quickAppsByDevice };
    if (packages.length) byDevice[serial] = packages;
    else delete byDevice[serial];
    this.#quickAppsByDevice = byDevice;
    this.saveBrowserSettings();
    this.renderQuickApps();
  }

  private launchableApp(packageName: string): LaunchableAppDto | null {
    return this.#launchableApps.find((app) => app.packageName === packageName) ?? null;
  }

  private renderQuickApps(): void {
    const serial = this.elements.device.value;
    const configured = this.currentQuickAppPackages();
    const configuredSet = new Set(configured);
    const connected = this.#protocolSession !== null && this.#serverSession !== null;

    this.elements.quickAppHeader.replaceChildren();
    for (const packageName of this.#launchableAppsLoaded ? configured : []) {
      const app = this.launchableApp(packageName);
      const label = app?.label ?? packageName;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "quick-app-button";
      button.dataset.quickAppPackage = packageName;
      button.dataset.launching = String(this.#quickAppLaunching === packageName);
      button.textContent = label;
      button.disabled = !connected || app === null || this.#quickAppLaunching !== null;
      button.setAttribute("aria-label", `Open or bring ${label} to the active Android display`);
      button.title = app === null
        ? `${packageName} is not currently installed on this Android device.`
        : connected
          ? `Open or bring ${label} to the active Android display · ${packageName}`
          : `Connect the Android display to open ${label} · ${packageName}`;
      this.elements.quickAppHeader.append(button);
    }
    const configure = document.createElement("button");
    configure.id = "quick-app-configure";
    configure.type = "button";
    configure.className = "quick-app-configure-button";
    configure.textContent = "Add app";
    configure.title = "Open Quick applications settings";
    configure.setAttribute("aria-label", "Add a quick Android application");
    this.elements.quickAppHeader.append(configure);
    this.elements.quickAppHeader.hidden = false;

    this.elements.quickAppList.replaceChildren();
    if (!serial) {
      this.elements.quickAppList.append(this.quickAppEmptyState("Select an authorized Android device."));
    } else if (configured.length === 0) {
      const message = !this.#launchableAppsLoaded
        ? "Reading installed Android applications…"
        : this.#launchableAppsError
          ? "Installed applications could not be read."
          : this.#launchableApps.length
            ? "No quick applications configured."
            : "No launchable Android applications found.";
      this.elements.quickAppList.append(this.quickAppEmptyState(message));
    } else {
      configured.forEach((packageName, index) => {
        const app = this.launchableApp(packageName);
        const label = app?.label ?? packageName;
        const row = document.createElement("div");
        row.className = "quick-app-row";

        const order = document.createElement("span");
        order.className = "quick-app-order";
        order.textContent = String(index + 1);

        const select = document.createElement("select");
        select.dataset.quickAppIndex = String(index);
        select.setAttribute("aria-label", `Application for quick button ${index + 1}`);
        if (app === null) {
          const unavailable = document.createElement("option");
          unavailable.value = packageName;
          unavailable.textContent = `Not installed · ${packageName}`;
          select.append(unavailable);
        }
        for (const catalogApp of this.#launchableApps) {
          if (catalogApp.packageName !== packageName && configuredSet.has(catalogApp.packageName)) continue;
          const option = document.createElement("option");
          option.value = catalogApp.packageName;
          option.textContent = `${catalogApp.label} · ${catalogApp.packageName}`;
          select.append(option);
        }
        select.value = packageName;
        select.disabled = !this.#launchableAppsLoaded || this.#launchableAppsError !== null || this.#launchableApps.length === 0;

        const actions = document.createElement("div");
        actions.className = "quick-app-row-actions";
        actions.append(
          this.quickAppActionButton("up", index, "↑", `Move ${label} earlier`, index === 0),
          this.quickAppActionButton("down", index, "↓", `Move ${label} later`, index === configured.length - 1),
          this.quickAppActionButton("remove", index, "×", `Remove ${label}`, false),
        );
        row.append(order, select, actions);
        this.elements.quickAppList.append(row);
      });
    }

    const nextPackage = nextQuickAppPackage(configured, this.#launchableApps);
    this.elements.quickAppAdd.disabled = !serial
      || !this.#launchableAppsLoaded
      || this.#launchableAppsError !== null
      || configured.length >= MAX_QUICK_APP_BUTTONS
      || nextPackage === null;
    if (!serial) {
      this.elements.quickAppSettingsStatus.textContent = "Quick applications are stored separately for each Android device.";
    } else if (!this.#launchableAppsLoaded) {
      this.elements.quickAppSettingsStatus.textContent = "Reading installed Android applications…";
    } else if (this.#launchableAppsError) {
      this.elements.quickAppSettingsStatus.textContent = `Installed-app query failed: ${this.#launchableAppsError}`;
    } else {
      this.elements.quickAppSettingsStatus.textContent = `${configured.length} of ${MAX_QUICK_APP_BUTTONS} quick application button(s) configured for this device.`;
    }
  }

  private quickAppEmptyState(message: string): HTMLElement {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = message;
    return empty;
  }

  private quickAppActionButton(
    action: "up" | "down" | "remove",
    index: number,
    text: string,
    label: string,
    disabled: boolean,
  ): HTMLButtonElement {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary compact";
    button.dataset.quickAppAction = action;
    button.dataset.quickAppIndex = String(index);
    button.textContent = text;
    button.title = label;
    button.setAttribute("aria-label", label);
    button.disabled = disabled;
    return button;
  }

  private addQuickApp(): void {
    const configured = this.currentQuickAppPackages();
    const packageName = nextQuickAppPackage(configured, this.#launchableApps);
    if (!packageName || configured.length >= MAX_QUICK_APP_BUTTONS) return;
    const app = this.launchableApp(packageName);
    this.setCurrentQuickAppPackages([...configured, packageName]);
    this.elements.quickAppSettingsStatus.textContent = `${app?.label ?? packageName} was added to the header.`;
  }

  private handleQuickAppSelection(event: Event): void {
    const select = event.target;
    if (!(select instanceof HTMLSelectElement) || !select.dataset.quickAppIndex) return;
    const index = Number(select.dataset.quickAppIndex);
    const packageName = select.value;
    const configured = [...this.currentQuickAppPackages()];
    if (
      !Number.isInteger(index)
      || index < 0
      || index >= configured.length
      || this.launchableApp(packageName) === null
      || configured.some((candidate, candidateIndex) => candidateIndex !== index && candidate === packageName)
    ) {
      this.renderQuickApps();
      return;
    }
    configured[index] = packageName;
    const app = this.launchableApp(packageName);
    this.setCurrentQuickAppPackages(configured);
    this.elements.quickAppSettingsStatus.textContent = `Quick button ${index + 1} now opens ${app?.label ?? packageName}.`;
  }

  private handleQuickAppAction(event: Event): void {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest<HTMLButtonElement>("button[data-quick-app-action]");
    if (!button || !this.elements.quickAppList.contains(button)) return;
    const index = Number(button.dataset.quickAppIndex);
    const action = button.dataset.quickAppAction;
    const configured = [...this.currentQuickAppPackages()];
    if (!Number.isInteger(index) || index < 0 || index >= configured.length) return;
    const packageName = configured[index]!;
    if (action === "remove") configured.splice(index, 1);
    else if (action === "up" || action === "down") {
      const reordered = moveQuickApp(configured, index, action === "up" ? -1 : 1);
      configured.splice(0, configured.length, ...reordered);
    } else return;
    this.setCurrentQuickAppPackages(configured);
    const label = this.launchableApp(packageName)?.label ?? packageName;
    this.elements.quickAppSettingsStatus.textContent = action === "remove"
      ? `${label} was removed from the header.`
      : `${label} was reordered.`;
  }

  private async handleQuickAppHeaderClick(event: Event): Promise<void> {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const configure = target.closest<HTMLButtonElement>("#quick-app-configure");
    if (configure && this.elements.quickAppHeader.contains(configure)) {
      this.openQuickAppSettings();
      return;
    }
    const button = target.closest<HTMLButtonElement>("button[data-quick-app-package]");
    if (!button || !this.elements.quickAppHeader.contains(button)) return;
    const packageName = button.dataset.quickAppPackage;
    if (packageName) await this.launchQuickApp(packageName);
  }

  private openQuickAppSettings(): void {
    document.querySelector<HTMLButtonElement>('#gb-single-drawer-root [data-group="settings"]')?.click();
    window.requestAnimationFrame(() => document.querySelector<HTMLElement>("#quick-app-settings")?.scrollIntoView({ block: "start" }));
  }

  private async launchQuickApp(packageName: string): Promise<void> {
    if (this.#quickAppLaunching) return;
    const app = this.launchableApp(packageName);
    const server = this.#serverSession;
    if (!app) throw new Error(`${packageName} is not installed on the selected Android device`);
    if (!server || !this.#protocolSession) throw new Error("Connect the Android display before opening a quick application");
    const display = server.displayMode === "virtual"
      ? `virtual display ${server.virtualDisplay.displayId ?? "pending"}`
      : "the phone screen (display 0)";
    this.#quickAppLaunching = packageName;
    this.renderQuickApps();
    this.setStatus("Opening application", `Requesting ${app.label} on ${display}…`);
    try {
      if (server.displayMode === "virtual" && server.virtualDisplay.displayId !== null) {
        try {
          const running = await this.#api.runningApps(server.serial);
          const task = [...running.apps]
            .filter((candidate) => candidate.packageName === packageName)
            .sort((left, right) => Number(right.resumed) - Number(left.resumed) || Number(right.visible) - Number(left.visible))[0];
          if (task) {
            const result = await this.#api.moveRunningApp({
              sessionId: server.sessionId,
              taskId: task.taskId,
              componentName: task.componentName,
            });
            this.setStatus(
              result.verified ? "Application ready" : "Application requested",
              result.verified
                ? `${app.label} is on ${display}.`
                : `Android was asked to bring ${app.label} to ${display}; relocation is not confirmed yet.`,
            );
            return;
          }
        } catch (error) {
          // A stale task snapshot or OEM-specific task parser must not make the
          // shortcut unusable. StartApp below is the authoritative launch path
          // and still targets this scrcpy session's physical/virtual display.
          console.warn("Running quick application could not be relocated; falling back to StartApp", error);
        }
      }
      await this.sendMessages([{ type: ControlMessageType.StartApp, name: packageName }]);
      this.setStatus("Application requested", `Android was asked to open or bring ${app.label} to ${display}.`);
    } finally {
      this.#quickAppLaunching = null;
      this.renderQuickApps();
    }
  }

  private startFlexResize(values: DisplayFormValues): void {
    this.stopFlexResize();
    this.#lastRequestedSize = { width: values.width, height: values.height };
    this.#resizeObserver = new ResizeObserver(() => {
      if (this.#resizeTimer !== null) window.clearTimeout(this.#resizeTimer);
      this.#resizeTimer = window.setTimeout(() => void this.runUiAction(() => this.applyFlexResize(values)), 250);
    });
    this.#resizeObserver.observe(this.elements.stage);
  }

  private stopFlexResize(): void {
    this.#resizeObserver?.disconnect();
    this.#resizeObserver = null;
    if (this.#resizeTimer !== null) window.clearTimeout(this.#resizeTimer);
    this.#resizeTimer = null;
    this.#lastRequestedSize = null;
  }

  private async applyFlexResize(values: DisplayFormValues): Promise<void> {
    const protocol = this.#protocolSession;
    const server = this.#serverSession;
    if (!protocol || !server || server.displayMode !== "virtual" || values.sizeMode !== "flex") return;
    const elapsed = Date.now() - this.#lastResizeAt;
    if (elapsed < 500) {
      this.#resizeTimer = window.setTimeout(() => void this.runUiAction(() => this.applyFlexResize(values)), 500 - elapsed);
      return;
    }
    const rect = this.elements.stage.getBoundingClientRect();
    const target = alignedFlexSize(rect.width - 24, rect.height - 24, values.width, values.height, values.preserveAspectRatio);
    const previous = this.#lastRequestedSize;
    if (previous && Math.abs(target.width - previous.width) < 16 && Math.abs(target.height - previous.height) < 16) return;
    this.#lastRequestedSize = target;
    this.#lastResizeAt = Date.now();
    this.setStatus("Resizing virtual display", `Requesting ${target.width}×${target.height}…`);
    await protocol.sendControl({ type: ControlMessageType.ResizeDisplay, width: target.width, height: target.height });
    await this.#api.recordVirtualResize(server.sessionId, target.width, target.height);
  }

  private async pointer(event: PointerEvent, action: number): Promise<void> {
    if (!this.#protocolSession) return;
    event.preventDefault();
    if (action === 0) {
      this.elements.canvas.setPointerCapture(event.pointerId);
      this.elements.canvas.focus();
    }
    const size = this.#renderer.screenSize;
    if (size.width <= 0 || size.height <= 0) return;
    const position = mapClientPoint(event.clientX, event.clientY, this.elements.canvas.getBoundingClientRect(), size);
    await this.#protocolSession.sendControl({
      type: ControlMessageType.InjectTouchEvent,
      action,
      pointerId: BigInt(event.pointerId),
      position,
      pressure: action === 1 || action === 3 ? 0 : Math.max(0.01, event.pressure || 1),
      actionButton: 0,
      buttons: event.buttons,
    });
    if ((action === 1 || action === 3) && this.elements.canvas.hasPointerCapture(event.pointerId)) {
      this.elements.canvas.releasePointerCapture(event.pointerId);
    }
  }

  private async scroll(event: WheelEvent): Promise<void> {
    if (!this.#protocolSession) return;
    event.preventDefault();
    const size = this.#renderer.screenSize;
    if (size.width <= 0 || size.height <= 0) return;
    const position = mapClientPoint(event.clientX, event.clientY, this.elements.canvas.getBoundingClientRect(), size);
    await this.#protocolSession.sendControl({
      type: ControlMessageType.InjectScrollEvent,
      position,
      horizontal: clamp(-event.deltaX / 80, -16, 16),
      vertical: clamp(-event.deltaY / 80, -16, 16),
      buttons: event.buttons,
    });
  }

  private async keydown(event: KeyboardEvent): Promise<void> {
    // Clipboard shortcuts are document-level so drawer focus cannot silently
    // disable them. Ctrl+V stays on the native paste event.
    const messages = keyboardMessages(event);
    if (!messages.length) return;
    event.preventDefault();
    await this.sendMessages(messages);
  }

  private async rotate(): Promise<void> {
    if (!this.#protocolSession) return;
    const previous = this.#renderer.screenSize;
    this.elements.rotate.disabled = true;
    this.setStatus("Rotating", "Restarting the scrcpy video capture session…");
    try {
      const resized = this.#renderer.waitForScreenSizeChange(previous);
      await this.sendMessages([{ type: ControlMessageType.RotateDevice }]);
      const size = await resized;
      this.setStatus("Connected", `Rotation completed · ${size.width}×${size.height}`);
    } catch (error) {
      this.setStatus("Rotation not confirmed", `${errorMessage(error)}. The session remains connected.`);
    } finally {
      if (this.#protocolSession) this.elements.rotate.disabled = false;
    }
  }

  private async togglePower(): Promise<void> {
    const nextPowerOn = !this.#powerOn;
    await this.sendMessages([{ type: ControlMessageType.SetDisplayPower, on: nextPowerOn }]);
    this.#powerOn = nextPowerOn;
    this.updatePowerButton();
  }

  private updatePowerButton(): void {
    const state = this.#powerOn ? "on" : "off";
    const action = this.#powerOn ? "Turn Android screen off" : "Turn Android screen on";
    this.elements.power.dataset.screenState = state;
    this.elements.power.setAttribute("aria-label", action);
    this.elements.power.title = action;
  }

  private async pasteClipboard(source = "PC clipboard"): Promise<void> {
    if (!this.#protocolSession) return;
    let text = "";
    try {
      text = await navigator.clipboard.readText();
    } catch {
      text = this.elements.clipboardText.value;
      if (!text) throw new Error("Browser clipboard permission was denied. Paste text into the fallback box, then press Type.");
    }
    if (!text) text = this.elements.clipboardText.value;
    if (!text) throw new Error("The PC clipboard is empty. Click the Android input field first, then copy text or use the fallback box.");
    this.elements.clipboardText.value = text;
    await this.pasteText(text, source);
  }

  private async pasteTypedText(): Promise<void> {
    const text = this.elements.clipboardText.value;
    if (!text) throw new Error("Enter or paste text into the fallback box first");
    const maximum = Math.max(1, Math.min(256, Number(this.elements.clipboardMaxKib.value) || 256)) * 1024;
    const bytes = new TextEncoder().encode(text).byteLength;
    if (bytes > maximum) throw new Error(`Text exceeds the configured ${maximum / 1024} KiB limit`);
    if (bytes > MAX_INJECTED_BYTES) {
      throw new Error(`Text is too large to type into Android (${Math.ceil(bytes / 1024)} KiB). Use Paste, which synchronizes the clipboard instead of typing.`);
    }
    this.setStatus("Typing", "Injecting the text box directly into the focused Android input field…");
    await this.sendMessages(textInjectionMessages(text));
    this.setStatus("Text typed", "Text box content was injected directly into Android without using the clipboard.");
  }

  private async pasteText(text: string, source: string): Promise<void> {
    const session = this.#protocolSession;
    const maximum = Math.max(1, Math.min(256, Number(this.elements.clipboardMaxKib.value) || 256)) * 1024;
    const bytes = new TextEncoder().encode(text).byteLength;
    if (bytes > maximum) throw new Error(`Clipboard text exceeds the configured ${maximum / 1024} KiB limit`);
    if (!session) return;
    const inject = bytes <= MAX_INJECTED_BYTES;
    const sequence = this.#clipboardSequence++;
    this.setStatus("Pasting", inject
      ? `Synchronizing ${source} and injecting it into the focused Android input field…`
      : `Synchronizing ${source} with the Android clipboard…`);
    const acknowledgement = this.waitForClipboardAcknowledgement(sequence);
    try {
      // SetClipboard(paste=true) only proves that Android processed the clipboard
      // message; its ACK does not prove KEYCODE_PASTE inserted anything. Keep the
      // clipboard synchronized with paste=false, then use scrcpy InjectText as the
      // deterministic insertion path (the same strategy as scrcpy legacy paste).
      await session.sendControl(clipboardMessage(text, sequence, false));
      if (inject) await this.sendMessages(textInjectionMessages(text));
      if (await acknowledgement) {
        this.#lastSentClipboard = text;
        this.setStatus(inject ? "Text pasted" : "Clipboard synchronized", inject
          ? `${source} was injected directly and the Android clipboard synchronization was acknowledged.`
          : `${source} is on the Android clipboard. It is too large to type, so paste it on the device.`);
      } else {
        this.setStatus("Text sent", inject
          ? `${source} was injected directly, but Android clipboard synchronization was not acknowledged.`
          : `${source} was sent to the Android clipboard but not acknowledged. If it arrived, paste it on the device.`);
      }
    } catch (error) {
      this.resolveClipboardAcknowledgement(sequence, false);
      throw error;
    }
  }

  private waitForClipboardAcknowledgement(sequence: bigint, timeoutMs = 3_000): Promise<boolean> {
    return new Promise((resolve) => {
      const waiter: ClipboardAckWaiter = {
        resolve,
        timer: window.setTimeout(() => this.resolveClipboardAcknowledgement(sequence, false), timeoutMs),
      };
      this.#clipboardAcks.set(sequence, waiter);
    });
  }

  private resolveClipboardAcknowledgement(sequence: bigint, acknowledged: boolean): void {
    const waiter = this.#clipboardAcks.get(sequence);
    if (!waiter) return;
    window.clearTimeout(waiter.timer);
    this.#clipboardAcks.delete(sequence);
    waiter.resolve(acknowledged);
  }

  private async toggleFullscreen(): Promise<void> {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await this.elements.stage.requestFullscreen();
  }

  private async sendMessages(messages: readonly ControlMessage[]): Promise<void> {
    const session = this.#protocolSession;
    if (!session) return;
    for (const message of messages) await session.sendControl(message);
  }

  private async consumeDeviceMessages(session: ScrcpyV41Session): Promise<void> {
    while (this.#protocolSession === session) {
      const message = await session.readDeviceMessage();
      if (message.type === DeviceMessageType.AckClipboard) {
        this.resolveClipboardAcknowledgement(message.sequence, true);
        continue;
      }
      if (message.type === DeviceMessageType.Clipboard) {
        if (this.#manualCopyDuplicate.consume(message.text, performance.now())) continue;
        const maximum = Math.max(1, Math.min(256, Number(this.elements.clipboardMaxKib.value) || 256)) * 1024;
        if (new TextEncoder().encode(message.text).byteLength > maximum) {
          this.setStatus("Clipboard skipped", `Android clipboard exceeds the configured ${maximum / 1024} KiB limit.`);
          continue;
        }
        this.#lastAndroidClipboard = message.text;
        this.elements.clipboardText.value = message.text;
        const copyShortcut = this.completeAndroidCopyRequest();
        if (copyShortcut) this.#manualCopyDuplicate.arm(message.text, performance.now());
        if (this.elements.clipboardAutoSync.checked || copyShortcut) {
          try {
            await navigator.clipboard.writeText(message.text);
            this.setStatus(copyShortcut ? "Clipboard copied" : "Clipboard synchronized", copyShortcut
              ? "Ctrl+C copied the Android selection to the PC clipboard."
              : "Android clipboard was copied to the PC clipboard.");
          } catch {
            this.setStatus(CLIPBOARD_STATUS.received, "Android clipboard is available in the clipboard panel; browser write permission was unavailable.");
          }
        } else {
          this.setStatus(CLIPBOARD_STATUS.received, "Android clipboard is available in the clipboard panel.");
        }
      }
    }
  }

  private async handleStreamFailure(error: unknown): Promise<void> {
    if (this.#closing) return;
    const message = errorMessage(error);
    await this.cleanupSession();
    this.setConnectedControls(false);
    this.setStatus("Stream stopped", message);
    if (!this.#manualDisconnect && this.elements.autoReconnect.checked) this.scheduleReconnect();
  }

  private async cleanupSession(): Promise<void> {
    this.stopFlexResize();
    const protocol = this.#protocolSession;
    const transport = this.#transport;
    const server = this.#serverSession;
    this.#protocolSession = null;
    this.#transport = null;
    this.#deviceMessageTask = null;
    this.#serverSession = null;
    this.#renderer.stop();
    this.#audioPlayer.stop();
    this.#audioTask = null;
    this.stopClipboardPolling();
    this.resetClipboardSessionState();
    for (const sequence of [...this.#clipboardAcks.keys()]) this.resolveClipboardAcknowledgement(sequence, false);
    try {
      await protocol?.close();
    } catch {
      await transport?.close();
    }
    if (server) {
      try {
        await this.#api.stopSession(server.sessionId);
      } catch {
        // The WebSocket endpoint may already have stopped the session.
      }
    }
  }

  private setConnectedControls(connected: boolean): void {
    this.elements.connect.textContent = connected ? "Disconnect" : "Connect";
    this.elements.connect.classList.toggle("danger", connected);
    this.elements.connect.disabled = false;
    for (const button of [
      this.elements.back,
      this.elements.home,
      this.elements.recent,
      this.elements.rotate,
      this.elements.power,
      this.elements.clipboard,
      this.elements.clipboardTextPaste,
      this.elements.fullscreen,
      this.elements.clipboardCopyAndroid,
    ]) button.disabled = !connected;
    this.elements.clipboardText.disabled = !connected;
    this.elements.audioMute.disabled = !connected || !this.elements.audioEnabled.checked;
    this.elements.audioVolume.disabled = !connected || !this.elements.audioEnabled.checked;
    this.elements.audioEnabled.disabled = connected;
    this.elements.reconnect.disabled = connected || !this.elements.device.value;
    this.elements.displayMode.disabled = connected;
    this.elements.displayProfile.disabled = connected;
    for (const input of this.displayInputs()) input.disabled = connected;
    this.renderQuickApps();
    if (!connected) this.updateDisplayUi();
  }

  private setBusy(busy: boolean): void {
    if (busy) this.elements.connect.disabled = true;
  }

  private setStatus(title: string, details: string): void {
    this.elements.status.textContent = title;
    this.elements.details.textContent = details;
    this.elements.statusContainer.title = details;

    const connecting = !this.#serverSession && (title === "Starting" || title.startsWith("Reconnect"));
    const connected = this.#serverSession !== null;
    const state = connected ? "connected" : connecting ? "connecting" : "disconnected";
    this.elements.statusContainer.dataset.state = state;
    this.elements.statusIcon.dataset.state = state;
    this.elements.statusContainer.setAttribute("aria-label", `${state}: ${title}. ${details}`);
  }

  private updateStatistics(stats: VideoStatistics): void {
    this.#latestStatistics = stats;
    this.elements.statistics.textContent = `${stats.width}×${stats.height} · video decoded ${stats.framesDecoded} · dropped ${stats.framesDropped} · queue ${stats.decoderQueue} · sessions ${stats.sessionChanges + 1}`;
    this.updateChannelStatus();
  }

  private updateAudioStatistics(stats: AudioStatistics): void {
    this.#latestAudioStatistics = stats;
    this.elements.audioStatus.textContent = `${stats.codec} · ${stats.packetsDecoded} packets · ${stats.bufferedMilliseconds} ms buffered${stats.muted ? " · muted" : ""}`;
    this.updateChannelStatus();
  }

  private updateChannelStatus(): void {
    const channels = this.#serverSession?.channels ?? [];
    const audio = this.#latestAudioStatistics ? ` · audio ${this.#latestAudioStatistics.codec}` : "";
    this.elements.sessionChannels.textContent = channels.length ? `Channels: ${channels.join(", ")}${audio}` : "No active channels.";
  }

  private toggleAudioMute(): void {
    const muted = this.elements.audioMute.textContent !== "Unmute";
    this.#audioPlayer.setMuted(muted);
    this.elements.audioMute.textContent = muted ? "Unmute" : "Mute";
    this.saveBrowserSettings();
  }

  private setAudioVolume(): void {
    this.#audioPlayer.setVolume(Number(this.elements.audioVolume.value) / 100);
    this.saveBrowserSettings();
  }

  private async copyAndroidClipboard(): Promise<void> {
    if (!this.#protocolSession) return;
    this.beginAndroidCopyRequest("Copy");
    await this.sendMessages([androidClipboardCopyMessage()]);
  }

  private beginAndroidCopyRequest(source: string): void {
    if (this.#copyShortcutTimer !== null) window.clearTimeout(this.#copyShortcutTimer);
    this.#copyShortcutPending = true;
    this.#copyShortcutTimer = window.setTimeout(() => {
      this.#copyShortcutTimer = null;
      if (!this.#copyShortcutPending) return;
      this.#copyShortcutPending = false;
      if (!this.#protocolSession) return;
      this.setStatus(CLIPBOARD_STATUS.notConfirmed, `Android did not report a clipboard update for ${source}. The previous PC clipboard was left unchanged.`);
    }, 1_200);
    this.setStatus(CLIPBOARD_STATUS.copying, `Requesting ${source} from the focused Android selection…`);
  }

  private completeAndroidCopyRequest(): boolean {
    const pending = this.#copyShortcutPending;
    this.#copyShortcutPending = false;
    if (this.#copyShortcutTimer !== null) window.clearTimeout(this.#copyShortcutTimer);
    this.#copyShortcutTimer = null;
    return pending;
  }

  private resetClipboardSessionState(): void {
    // Cached device clipboard state must not leak across sessions. The visible
    // text box is user input, not cached state, so it is deliberately left
    // alone: clearing it discards text typed while disconnected.
    this.#lastAndroidClipboard = "";
    this.#lastSentClipboard = "";
    this.#unacknowledgedSync = null;
    this.#manualCopyDuplicate.reset();
    this.completeAndroidCopyRequest();
  }

  private async startClipboardPolling(requestPermission: boolean): Promise<void> {
    this.stopClipboardPolling();
    this.#clipboardReadAllowed = false;
    if (!this.#protocolSession || !this.elements.clipboardAutoSync.checked) return;

    if (!navigator.clipboard?.readText) {
      this.setStatus("Clipboard sync limited", "This browser cannot read the PC clipboard automatically. Android → PC synchronization remains available.");
      return;
    }

    const armPolling = async (initial: string): Promise<void> => {
      this.#clipboardReadAllowed = true;
      if (initial && initial !== this.#lastSentClipboard && initial !== this.#lastAndroidClipboard) {
        await this.synchronizePcClipboard(initial);
      }
      this.#clipboardPollTimer = window.setInterval(() => void this.pollPcClipboard(), 1800);
    };

    if (requestPermission) {
      try {
        // Keep this as the first awaited browser API call from the checkbox
        // gesture. Firefox does not expose clipboard-read through Permissions,
        // and delaying readText() can lose the transient user activation.
        await armPolling(await navigator.clipboard.readText());
      } catch {
        this.#clipboardReadAllowed = false;
        this.setStatus("Clipboard sync limited", "Browser clipboard permission was not granted. Use Paste or Type manually; Android → PC synchronization remains active.");
      }
      return;
    }

    let permissionState: PermissionState | "unsupported" = "unsupported";
    if (navigator.permissions?.query) {
      try {
        const permission = await navigator.permissions.query({ name: "clipboard-read" as PermissionName });
        permissionState = permission.state;
      } catch {
        // Some browsers expose the Clipboard API but not clipboard-read through Permissions.
      }
    }

    if (permissionState === "denied") {
      this.setStatus("Clipboard sync limited", "Automatic PC → Android clipboard access is blocked by the browser. Use Paste or Type manually; Android → PC sync remains active.");
      return;
    }
    if (permissionState !== "granted") {
      // A reconnect/background restore must never trigger a clipboard permission
      // prompt. The checkbox gesture above is the only prompting path.
      this.setStatus("Clipboard sync ready", "Android → PC sync is active. Toggle automatic sync off/on once to grant PC → Android clipboard access.");
      return;
    }

    try {
      await armPolling(await navigator.clipboard.readText());
    } catch {
      this.#clipboardReadAllowed = false;
      this.setStatus("Clipboard sync limited", "Browser clipboard permission was not granted. Use Paste or Type manually; Android → PC synchronization remains active.");
    }
  }

  private stopClipboardPolling(): void {
    if (this.#clipboardPollTimer !== null) window.clearInterval(this.#clipboardPollTimer);
    this.#clipboardPollTimer = null;
    this.#clipboardPollBusy = false;
  }

  private async pollPcClipboard(): Promise<void> {
    if (!document.hasFocus() || !this.#protocolSession || !this.elements.clipboardAutoSync.checked || !this.#clipboardReadAllowed || this.#clipboardPollBusy) return;
    this.#clipboardPollBusy = true;
    try {
      const text = await navigator.clipboard.readText();
      if (!text || text === this.#lastSentClipboard || text === this.#lastAndroidClipboard) return;
      await this.synchronizePcClipboard(text);
    } catch {
      // Stop polling after the first runtime permission failure instead of repeatedly opening
      // browser clipboard/paste UI and stealing focus from PC keyboard input to Android.
      this.#clipboardReadAllowed = false;
      this.stopClipboardPolling();
      this.setStatus("Clipboard sync limited", "Automatic PC clipboard access stopped after a browser permission error. Use Paste manually or toggle sync to grant access again.");
    } finally {
      this.#clipboardPollBusy = false;
    }
  }

  private async synchronizePcClipboard(text: string): Promise<void> {
    const session = this.#protocolSession;
    if (!session) return;
    const maximum = Math.max(1, Math.min(256, Number(this.elements.clipboardMaxKib.value) || 256)) * 1024;
    if (new TextEncoder().encode(text).byteLength > maximum) {
      this.setStatus("Clipboard skipped", `PC clipboard exceeds the configured ${maximum / 1024} KiB limit.`);
      return;
    }
    const sequence = this.#clipboardSequence++;
    // Automatic synchronization updates Android's clipboard only.  It MUST NOT
    // request a paste action, because repeated paste=true messages steal focus
    // from the Android input method and make normal PC keyboard typing unusable.
    const acknowledgement = this.waitForClipboardAcknowledgement(sequence, 1_500);
    try {
      await session.sendControl(clipboardMessage(text, sequence, false));
      if (await acknowledgement) {
        this.#lastSentClipboard = text;
        this.#unacknowledgedSync = null;
        this.setStatus("Clipboard synchronized", "PC clipboard was acknowledged by Android without pasting into the focused field.");
      } else {
        const attempts = this.#unacknowledgedSync?.text === text ? this.#unacknowledgedSync.attempts + 1 : 1;
        this.#unacknowledgedSync = { text, attempts };
        if (attempts >= MAX_UNACKNOWLEDGED_SYNC_ATTEMPTS) {
          // Record it as sent so the poller stops retrying this text.
          this.#lastSentClipboard = text;
          this.setStatus("Clipboard sync gave up", `Android did not acknowledge the PC clipboard after ${attempts} attempts. Copy again or use Paste to retry.`);
        } else {
          this.setStatus("Clipboard sync not confirmed", "PC clipboard update was sent, but Android did not acknowledge it. It will be retried.");
        }
      }
    } catch (error) {
      this.resolveClipboardAcknowledgement(sequence, false);
      throw error;
    }
  }

  private scheduleReconnect(): void {
    this.cancelReconnect();
    const maximum = Number(this.elements.reconnectAttempts.value) || 5;
    if (this.#reconnectCount >= maximum) {
      this.setStatus("Reconnect stopped", `Unable to reconnect after ${maximum} attempts.`);
      return;
    }
    const delays = [1000, 2000, 5000, 10000, 15000];
    const delay = delays[Math.min(this.#reconnectCount, delays.length - 1)]!;
    this.#reconnectCount += 1;
    this.setStatus("Reconnect scheduled", `Attempt ${this.#reconnectCount} of ${maximum} in ${delay / 1000} seconds.`);
    this.#reconnectTimer = window.setTimeout(() => void this.runUiAction(async () => {
      try {
        await this.refreshDevices();
        await this.connect();
      } catch (error) {
        if (this.elements.autoReconnect.checked) this.scheduleReconnect();
        throw error;
      }
    }), delay);
  }

  private cancelReconnect(): void {
    if (this.#reconnectTimer !== null) window.clearTimeout(this.#reconnectTimer);
    this.#reconnectTimer = null;
  }

  private async reconnectNow(): Promise<void> {
    this.cancelReconnect();
    if (this.#serverSession) await this.cleanupSession();
    await this.refreshDevices();
    await this.connect();
  }


  private browserSettings(): Record<string, unknown> {
    return {
      schemaVersion: 1,
      display: this.readDisplayValues(),
      audio: { enabled: this.elements.audioEnabled.checked, muted: this.elements.audioMute.textContent === "Unmute", volume: Number(this.elements.audioVolume.value) },
      clipboard: { automatic: this.elements.clipboardAutoSync.checked, maximumKiB: Number(this.elements.clipboardMaxKib.value) },
      reconnect: { enabled: this.elements.autoReconnect.checked, attempts: Number(this.elements.reconnectAttempts.value) },
      quickApps: { byDevice: this.#quickAppsByDevice },
    };
  }

  private saveBrowserSettings(): void {
    localStorage.setItem("droidwebdisplay-settings-v1", JSON.stringify(this.browserSettings()));
  }

  private restoreBrowserSettings(): void {
    try {
      const raw = localStorage.getItem("droidwebdisplay-settings-v1");
      if (!raw) return;
      this.applyImportedSettings(JSON.parse(raw) as Record<string, unknown>);
    } catch {
      localStorage.removeItem("droidwebdisplay-settings-v1");
    }
  }

  private applyImportedSettings(value: Record<string, unknown>): void {
    const display = value.display as Record<string, unknown> | undefined;
    const audio = value.audio as Record<string, unknown> | undefined;
    const clipboard = value.clipboard as Record<string, unknown> | undefined;
    const reconnect = value.reconnect as Record<string, unknown> | undefined;
    const quickApps = value.quickApps as Record<string, unknown> | undefined;
    if (display) {
      const mode = display.displayMode === "virtual" ? "virtual" : "physical";
      this.elements.displayMode.value = mode;
      this.elements.displayProfile.value = typeof display.profileId === "string" ? display.profileId : "custom";
      this.elements.sizeMode.value = display.sizeMode === "flex" ? "flex" : "fixed";
      this.elements.virtualWidth.value = String(Number(display.width) || 1600);
      this.elements.virtualHeight.value = String(Number(display.height) || 900);
      this.elements.virtualDpi.value = String(Number(display.dpi) || 240);
      this.elements.manualApp.value = typeof display.startApp === "string" ? display.startApp : "com.openai.chatgpt";
      this.elements.forceStop.checked = display.forceStopBeforeLaunch === true;
      this.elements.keepActive.checked = display.keepActive !== false;
      this.elements.systemDecorations.checked = display.systemDecorations !== false;
      this.elements.destroyContent.checked = display.destroyContentOnClose !== false;
      const savedImePolicy = ["default", "local", "fallback", "hide"].includes(String(display.imePolicy)) ? String(display.imePolicy) : "default";
      this.elements.hideVirtualKeyboard.checked = savedImePolicy === "hide";
      this.elements.imePolicy.value = savedImePolicy === "hide" ? "default" : savedImePolicy;
      this.elements.preserveAspect.checked = display.preserveAspectRatio !== false;
      this.elements.videoBitrate.value = String(Number(display.videoBitRateMbps) || 12);
      this.elements.virtualMaxFps.value = String(Number(display.maxFps) || 60);
      this.updateDisplayUi();
    }
    this.elements.audioEnabled.checked = audio?.enabled === true;
    this.elements.audioVolume.value = String(Math.max(0, Math.min(100, Number(audio?.volume ?? 100))));
    this.elements.audioMute.textContent = audio?.muted === true ? "Unmute" : "Mute";
    this.elements.clipboardAutoSync.checked = clipboard?.automatic === true;
    this.elements.clipboardMaxKib.value = String(Math.max(1, Math.min(256, Number(clipboard?.maximumKiB ?? 256))));
    this.elements.autoReconnect.checked = reconnect?.enabled !== false;
    this.elements.reconnectAttempts.value = String([3, 5, 10].includes(Number(reconnect?.attempts)) ? Number(reconnect?.attempts) : 5);
    this.#quickAppsByDevice = normalizeQuickAppsByDevice(quickApps?.byDevice);
    this.renderQuickApps();
  }

  private exportSettings(): void {
    this.downloadJson("droidwebdisplay-settings.json", this.browserSettings());
    this.elements.settingsStatus.textContent = "Settings exported.";
  }

  private async importSettings(): Promise<void> {
    const file = this.elements.settingsFile.files?.[0];
    if (!file) return;
    const parsed = JSON.parse(await file.text()) as Record<string, unknown>;
    if (parsed.schemaVersion !== 1) throw new Error("Unsupported settings file version");
    this.applyImportedSettings(parsed);
    this.saveBrowserSettings();
    this.elements.settingsStatus.textContent = "Settings imported. Quick application buttons are updated; reconnect to apply session options.";
    this.elements.settingsFile.value = "";
  }

  private downloadJson(filename: string, value: unknown): void {
    const blob = new Blob([`${JSON.stringify(value, null, 2)}\n`], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  private async runUiAction(action: () => Promise<void>): Promise<void> {
    try {
      await action();
    } catch (error) {
      this.setStatus("Error", errorMessage(error));
    }
  }
}

function deviceLabel(device: AndroidDevice): string {
  const name = device.model ?? device.serial;
  const version = device.android_version ? `Android ${device.android_version}` : device.state;
  return `${name} · ${version}${device.ready ? "" : ` · ${device.state}`}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.max(minimum, Math.min(maximum, value));
}
