import {
  ControlMessageType,
  DeviceMessageType,
  ScrcpyV41Adapter,
  type ControlMessage,
  type ScrcpyV41Session,
} from "@droid-web-display/scrcpy-protocol";
import { BridgeApi, type StartSessionRequest } from "./api.js";
import {
  alignedFlexSize,
  buildSessionRequest,
  validateDisplayForm,
  VIRTUAL_DISPLAY_PROFILES,
  type DisplayFormValues,
} from "./display-config.js";
import { androidClipboardCopyMessage, androidKeyPress, clipboardMessage, clipboardShortcut, keyboardMessages, mapClientPoint, textInjectionMessages } from "./input.js";
import type { AndroidDevice, SessionDto, VirtualDisplayCapabilities } from "./types.js";
import { WebCodecsVideoRenderer, type VideoStatistics } from "./video-renderer.js";
import { WebSocketBridgeTransport } from "./websocket-transport.js";
import { WebCodecsAudioPlayer, type AudioStatistics } from "./audio-player.js";

interface ClipboardAckWaiter {
  readonly resolve: (acknowledged: boolean) => void;
  readonly timer: number;
}

interface Elements {
  readonly device: HTMLSelectElement;
  readonly refresh: HTMLButtonElement;
  readonly connect: HTMLButtonElement;
  readonly disconnect: HTMLButtonElement;
  readonly canvas: HTMLCanvasElement;
  readonly stage: HTMLElement;
  readonly stageHint: HTMLElement;
  readonly tabs: HTMLElement;
  readonly tabAdd: HTMLButtonElement;
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
  readonly displayName: HTMLInputElement;
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
  readonly restoreProfile: HTMLButtonElement;
}

interface DisplayRuntime {
  serverSession: SessionDto;
  readonly transport: WebSocketBridgeTransport;
  readonly protocolSession: ScrcpyV41Session;
  readonly renderer: WebCodecsVideoRenderer;
  readonly audioPlayer: WebCodecsAudioPlayer;
  readonly canvas: HTMLCanvasElement;
  readonly values: DisplayFormValues;
  audioTask: Promise<void> | null;
  deviceMessageTask: Promise<void> | null;
  latestStatistics: VideoStatistics | null;
  latestAudioStatistics: AudioStatistics | null;
  lastAndroidClipboard: string;
  lastSentClipboard: string;
}

export class DroidWebDisplayController {
  readonly #api = new BridgeApi();
  readonly #adapter = new ScrcpyV41Adapter();
  #transport: WebSocketBridgeTransport | null = null;
  #protocolSession: ScrcpyV41Session | null = null;
  #serverSession: SessionDto | null = null;
  readonly #baseRenderer: WebCodecsVideoRenderer;
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
  #clipboardPollTimer: number | null = null;
  #clipboardReadAllowed = false;
  #clipboardPollBusy = false;
  #copyShortcutPending = false;
  #latestStatistics: VideoStatistics | null = null;
  #deviceMessageTask: Promise<void> | null = null;
  #capabilities: VirtualDisplayCapabilities | null = null;
  #resizeObserver: ResizeObserver | null = null;
  #resizeTimer: number | null = null;
  #lastResizeAt = 0;
  #lastRequestedSize: { width: number; height: number } | null = null;
  readonly #runtimes = new Map<string, DisplayRuntime>();
  #activeSessionId: string | null = null;
  readonly #clipboardAcks = new Map<bigint, ClipboardAckWaiter>();

  public constructor(private readonly elements: Elements) {
    this.#baseRenderer = new WebCodecsVideoRenderer(
      elements.canvas,
      (stats) => this.updateRuntimeStatistics(elements.canvas.dataset.sessionId ?? null, stats),
    );
    this.#renderer = this.#baseRenderer;
    this.#audioPlayer = new WebCodecsAudioPlayer(() => undefined);
    this.populateProfiles();
    this.bindEvents();
    this.bindCanvasEvents(elements.canvas);
    this.renderTabs();
  }

  public async initialize(): Promise<void> {
    this.applyProfile(localStorage.getItem("droidwebdisplay-virtual-profile-v1") ?? "chatgpt-desktop");
    this.restoreBrowserSettings();
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
    const previousOption = [...this.elements.device.options].find((option) => option.value === previous && !option.disabled);
    if (previousOption) previousOption.selected = true;
    this.updateConnectAvailability();
  }

  public async connect(): Promise<void> {
    const serial = this.elements.device.value;
    if (!serial) throw new Error("No authorized device is selected");
    const existingSerial = this.firstRuntime()?.serverSession.serial ?? null;
    if (existingSerial && existingSerial !== serial) {
      throw new Error("Close the current device display tabs before selecting another Android device");
    }
    const values = this.readDisplayValues();
    const errors = validateDisplayForm(values);
    if (errors.length) throw new Error(errors.join(" "));
    if (values.displayMode === "virtual" && !this.#capabilities?.virtualDisplaySupported) {
      throw new Error(this.#capabilities?.warnings.join(" ") || "Virtual Display mode is not supported by this device.");
    }

    const explicitDisplayName = this.elements.displayName.value.trim();
    const displayName = explicitDisplayName || this.automaticDisplayName(values);
    let serverSession: SessionDto | null = null;
    let transport: WebSocketBridgeTransport | null = null;
    let protocolSession: ScrcpyV41Session | null = null;
    let runtimeCanvas: HTMLCanvasElement | null = null;
    let renderer: WebCodecsVideoRenderer | null = null;
    let audioPlayer: WebCodecsAudioPlayer | null = null;

    this.setBusy(true);
    this.setStatus(
      this.#runtimes.size ? "Adding display" : "Starting",
      values.displayMode === "virtual" ? "Creating Android virtual display and opening browser channels…" : "Launching scrcpy and opening browser channels…",
    );
    try {
      const request = {
        ...buildSessionRequest(values, serial),
        displayName,
        audio: this.elements.audioEnabled.checked,
        audioCodec: "opus",
        audioBitRate: 128_000,
      } as StartSessionRequest;
      serverSession = await this.#api.startDeviceSession(serial, request);
      runtimeCanvas = this.allocateRuntimeCanvas(serverSession.sessionId);
      renderer = runtimeCanvas === this.elements.canvas
        ? this.#baseRenderer
        : new WebCodecsVideoRenderer(
          runtimeCanvas,
          (stats) => this.updateRuntimeStatistics(runtimeCanvas?.dataset.sessionId ?? null, stats),
        );
      audioPlayer = new WebCodecsAudioPlayer(
        (stats) => this.updateRuntimeAudioStatistics(serverSession?.sessionId ?? null, stats),
      );
      audioPlayer.setMuted(true);
      audioPlayer.setVolume(Number(this.elements.audioVolume.value) / 100);

      transport = new WebSocketBridgeTransport(serverSession.sessionId);
      protocolSession = await this.#adapter.connect(transport, {
        video: true,
        audio: this.elements.audioEnabled.checked,
        control: true,
      });

      const runtime: DisplayRuntime = {
        serverSession,
        transport,
        protocolSession,
        renderer,
        audioPlayer,
        canvas: runtimeCanvas,
        values,
        audioTask: null,
        deviceMessageTask: null,
        latestStatistics: null,
        latestAudioStatistics: null,
        lastAndroidClipboard: "",
        lastSentClipboard: "",
      };
      this.#runtimes.set(serverSession.sessionId, runtime);
      this.renderTabs();

      runtime.deviceMessageTask = this.consumeDeviceMessages(serverSession.sessionId, protocolSession);
      void runtime.deviceMessageTask.catch((error: unknown) => {
        if (this.#runtimes.has(serverSession!.sessionId)) console.warn("Control device-message stream ended", error);
      });
      void renderer.run(protocolSession).catch((error: unknown) => this.handleRuntimeFailure(serverSession!.sessionId, error));

      if (this.elements.audioEnabled.checked && protocolSession.audioHeader) {
        runtime.audioTask = audioPlayer.run(protocolSession);
        void runtime.audioTask.catch((error: unknown) => {
          if (this.#activeSessionId === serverSession!.sessionId) {
            this.elements.audioStatus.textContent = `Audio unavailable: ${errorMessage(error)}. Video and control remain active.`;
          }
        });
      }

      if (values.displayMode === "virtual" && values.startApp) {
        const payload = values.forceStopBeforeLaunch ? `+${values.startApp}` : values.startApp;
        await protocolSession.sendControl({ type: ControlMessageType.StartApp, name: payload });
        runtime.serverSession = await this.#api.recordApplicationLaunch(serverSession.sessionId, "sent");
      }

      this.activateRuntime(serverSession.sessionId);
      this.#reconnectCount = 0;
      this.renderTabs();
    } catch (error) {
      if (serverSession && this.#runtimes.has(serverSession.sessionId)) {
        await this.cleanupRuntime(serverSession.sessionId);
      } else {
        renderer?.stop();
        audioPlayer?.stop();
        try {
          await protocolSession?.close();
        } catch {
          await transport?.close();
        }
        if (runtimeCanvas) this.releaseRuntimeCanvas(runtimeCanvas);
        if (serverSession) {
          try {
            await this.#api.stopDeviceSession(serial, serverSession.sessionId);
          } catch {
            // The WebSocket endpoint may already have stopped the failed session.
          }
        }
      }
      if (this.#serverSession) this.updateActiveRuntimeStatus();
      else this.setStatus("Connection failed", errorMessage(error));
      this.setConnectedControls(this.#serverSession !== null);
      throw error;
    } finally {
      this.setBusy(false);
      this.updateConnectAvailability();
    }
  }

  public async disconnect(): Promise<void> {
    if (!this.#activeSessionId) return;
    this.#manualDisconnect = true;
    this.cancelReconnect();
    this.#closing = true;
    try {
      const closingName = this.#serverSession?.display.name ?? "display";
      await this.cleanupSession();
      if (this.#serverSession) this.updateActiveRuntimeStatus();
      else this.setStatus("Disconnected", `${closingName} was stopped. No display tabs remain.`);
    } finally {
      this.#closing = false;
      this.setConnectedControls(this.#serverSession !== null);
      this.#manualDisconnect = false;
    }
  }

  public stopOnUnload(): void {
    const serial = this.firstRuntime()?.serverSession.serial;
    if (!serial) return;
    void this.#api.stopDeviceSessions(serial, true);
  }

  private firstRuntime(): DisplayRuntime | null {
    return this.#runtimes.values().next().value ?? null;
  }

  private automaticDisplayName(values: DisplayFormValues): string {
    const sameKind = [...this.#runtimes.values()].filter((runtime) => runtime.serverSession.display.kind === values.displayMode);
    if (values.displayMode === "physical") return sameKind.length ? `Phone ${sameKind.length + 1}` : "Phone";
    const base = values.startApp === "com.openai.chatgpt"
      ? "ChatGPT"
      : values.startApp ? values.startApp.split(".").at(-1) || "Virtual display" : "Virtual display";
    const duplicateCount = [...this.#runtimes.values()].filter((runtime) => runtime.serverSession.display.name.startsWith(base)).length;
    return duplicateCount ? `${base} ${duplicateCount + 1}` : base;
  }

  private allocateRuntimeCanvas(sessionId: string): HTMLCanvasElement {
    if (![...this.#runtimes.values()].some((runtime) => runtime.canvas === this.elements.canvas)) {
      this.elements.canvas.dataset.sessionId = sessionId;
      this.elements.canvas.hidden = false;
      return this.elements.canvas;
    }
    const canvas = document.createElement("canvas");
    canvas.className = "display-canvas";
    canvas.tabIndex = 0;
    canvas.setAttribute("aria-label", "Android display session");
    canvas.dataset.sessionId = sessionId;
    canvas.hidden = true;
    this.bindCanvasEvents(canvas);
    this.elements.stage.insertBefore(canvas, this.elements.stageHint);
    return canvas;
  }

  private releaseRuntimeCanvas(canvas: HTMLCanvasElement): void {
    canvas.dataset.sessionId = "";
    canvas.hidden = true;
    if (canvas !== this.elements.canvas) canvas.remove();
    else if (this.#runtimes.size === 0) {
      canvas.hidden = false;
      const context = canvas.getContext?.("2d");
      context?.clearRect(0, 0, canvas.width, canvas.height);
    }
  }

  private bindCanvasEvents(canvas: HTMLCanvasElement): void {
    canvas.addEventListener("contextmenu", (event) => event.preventDefault());
    canvas.addEventListener("pointerdown", (event) => void this.pointer(event, 0));
    canvas.addEventListener("pointermove", (event) => {
      if (event.buttons !== 0) void this.pointer(event, 2);
    });
    canvas.addEventListener("pointerup", (event) => void this.pointer(event, 1));
    canvas.addEventListener("pointercancel", (event) => void this.pointer(event, 3));
    canvas.addEventListener("wheel", (event) => void this.scroll(event), { passive: false });
    canvas.addEventListener("keydown", (event) => void this.keydown(event));
    canvas.addEventListener("paste", (event) => {
      const text = event.clipboardData?.getData("text/plain") ?? "";
      if (!text) return;
      event.preventDefault();
      void this.runUiAction(() => this.pasteText(text, "Ctrl+V"));
    });
  }

  private renderTabs(): void {
    this.elements.tabs.replaceChildren();
    if (!this.#runtimes.size) {
      const empty = document.createElement("span");
      empty.className = "display-tabs-empty";
      empty.textContent = "No active displays";
      this.elements.tabs.append(empty);
      return;
    }
    const ids = [...this.#runtimes.keys()];
    for (const [sessionId, runtime] of this.#runtimes) {
      const identity = runtime.serverSession.display;
      const item = document.createElement("div");
      item.className = "display-tab";
      item.dataset.active = String(sessionId === this.#activeSessionId);

      const select = document.createElement("button");
      select.type = "button";
      select.className = "display-tab-select";
      select.setAttribute("role", "tab");
      select.setAttribute("aria-selected", String(sessionId === this.#activeSessionId));
      select.dataset.sessionId = sessionId;
      select.title = identity.application ? `${identity.name} · ${identity.application}` : identity.name;
      const kind = document.createElement("span");
      kind.className = "display-tab-kind";
      kind.textContent = identity.kind === "physical" ? "PHONE" : "VD";
      const name = document.createElement("span");
      name.className = "display-tab-name";
      name.textContent = identity.name;
      const meta = document.createElement("span");
      meta.className = "display-tab-meta";
      meta.textContent = identity.kind === "physical"
        ? "display 0 · live"
        : `display ${identity.displayId ?? "…"} · live`;
      select.append(kind, name, meta);
      select.addEventListener("click", () => this.activateRuntime(sessionId));
      select.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        const current = ids.indexOf(sessionId);
        const offset = event.key === "ArrowRight" ? 1 : -1;
        const next = ids[(current + offset + ids.length) % ids.length];
        if (next) this.activateRuntime(next);
      });

      const close = document.createElement("button");
      close.type = "button";
      close.className = "display-tab-close";
      close.textContent = "×";
      close.title = `Close ${identity.name}`;
      close.setAttribute("aria-label", `Close ${identity.name}`);
      close.addEventListener("click", () => void this.runUiAction(() => this.closeDisplayTab(sessionId)));
      item.append(select, close);
      this.elements.tabs.append(item);
    }
  }

  private activateRuntime(sessionId: string): void {
    const runtime = this.#runtimes.get(sessionId);
    if (!runtime) return;
    this.stopFlexResize();
    this.stopClipboardPolling();
    this.#activeSessionId = sessionId;
    this.#serverSession = runtime.serverSession;
    this.#transport = runtime.transport;
    this.#protocolSession = runtime.protocolSession;
    this.#renderer = runtime.renderer;
    this.#audioPlayer = runtime.audioPlayer;
    this.#audioTask = runtime.audioTask;
    this.#deviceMessageTask = runtime.deviceMessageTask;
    this.#latestStatistics = runtime.latestStatistics;
    this.#latestAudioStatistics = runtime.latestAudioStatistics;
    this.#lastAndroidClipboard = runtime.lastAndroidClipboard;
    this.#lastSentClipboard = runtime.lastSentClipboard;
    this.#lastConnectValues = runtime.values;

    const userMuted = this.elements.audioMute.textContent === "Unmute";
    for (const [id, value] of this.#runtimes) {
      value.canvas.hidden = id !== sessionId;
      value.audioPlayer.setMuted(id === sessionId ? userMuted : true);
    }
    this.elements.stageHint.hidden = true;
    this.renderTabs();
    this.setConnectedControls(true);
    if (runtime.values.displayMode === "virtual" && runtime.values.sizeMode === "flex") this.startFlexResize(runtime.values);
    this.updateActiveRuntimeStatus();
    if (runtime.latestStatistics) this.showStatistics(runtime.latestStatistics);
    else this.elements.statistics.textContent = "Waiting for video statistics";
    if (runtime.latestAudioStatistics) this.showAudioStatistics(runtime.latestAudioStatistics);
    else this.elements.audioStatus.textContent = runtime.protocolSession.audioHeader
      ? `Audio connected · ${runtime.protocolSession.audioHeader.codec}`
      : "Audio disabled or unavailable for this display.";
    this.updateChannelStatus();
    void this.startClipboardPolling(false);
    runtime.canvas.focus();
    globalThis.dispatchEvent(new CustomEvent("droidwebdisplay-active-session", { detail: { sessionId } }));
  }

  private clearActiveRuntime(): void {
    this.stopFlexResize();
    this.stopClipboardPolling();
    this.#activeSessionId = null;
    this.#serverSession = null;
    this.#transport = null;
    this.#protocolSession = null;
    this.#audioTask = null;
    this.#deviceMessageTask = null;
    this.#latestStatistics = null;
    this.#latestAudioStatistics = null;
    this.#lastAndroidClipboard = "";
    this.#lastSentClipboard = "";
    this.elements.stageHint.hidden = false;
    this.elements.statistics.textContent = "No video statistics";
    this.elements.audioStatus.textContent = "Audio disabled.";
    this.elements.sessionChannels.textContent = "No active channels.";
    this.renderTabs();
    this.setConnectedControls(false);
    globalThis.dispatchEvent(new CustomEvent("droidwebdisplay-active-session", { detail: { sessionId: null } }));
  }

  private updateActiveRuntimeStatus(): void {
    const runtime = this.#activeSessionId ? this.#runtimes.get(this.#activeSessionId) : null;
    if (!runtime) return;
    const display = runtime.serverSession.display;
    if (display.kind === "virtual") {
      const resolution = display.resolution.width && display.resolution.height
        ? `${display.resolution.width}×${display.resolution.height}`
        : `${runtime.values.width}×${runtime.values.height}`;
      const dpi = display.dpi.value ?? runtime.values.dpi;
      this.setStatus("Virtual display connected", `${display.name} · display ${display.displayId ?? "pending"} · ${resolution} · ${dpi} DPI`);
    } else {
      const deviceName = runtime.protocolSession.device?.name ?? runtime.serverSession.serial;
      this.setStatus("Connected", `${display.name} · ${deviceName} · H.264 · ${runtime.serverSession.options.maxFps} fps limit`);
    }
  }

  private async closeDisplayTab(sessionId: string): Promise<void> {
    const runtime = this.#runtimes.get(sessionId);
    if (!runtime) return;
    const name = runtime.serverSession.display.name;
    await this.cleanupRuntime(sessionId);
    if (!this.#serverSession) this.setStatus("Disconnected", `${name} was stopped. No display tabs remain.`);
  }

  private bindEvents(): void {
    this.elements.refresh.addEventListener("click", () => void this.runUiAction(async () => {
      await this.refreshDevices();
      await this.refreshVirtualCapabilities();
    }));
    this.elements.device.addEventListener("change", () => void this.runUiAction(() => this.refreshVirtualCapabilities()));
    this.elements.connect.addEventListener("click", () => void this.runUiAction(() => this.connect()));
    this.elements.tabAdd.addEventListener("click", () => void this.runUiAction(() => this.connect()));
    this.elements.disconnect.addEventListener("click", () => void this.runUiAction(() => this.disconnect()));
    this.elements.displayMode.addEventListener("change", () => this.updateDisplayUi());
    this.elements.displayProfile.addEventListener("change", () => {
      if (this.elements.displayProfile.value !== "custom") this.applyProfile(this.elements.displayProfile.value);
      this.updateDisplayUi();
    });
    this.elements.restoreProfile.addEventListener("click", () => {
      const id = this.elements.displayProfile.value === "custom" ? "chatgpt-desktop" : this.elements.displayProfile.value;
      this.applyProfile(id);
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
    this.elements.fullscreen.addEventListener("click", () => void this.toggleFullscreen());
    this.elements.audioMute.addEventListener("click", () => this.toggleAudioMute());
    this.elements.audioVolume.addEventListener("input", () => this.setAudioVolume());
    this.elements.audioEnabled.addEventListener("change", () => this.saveBrowserSettings());
    this.elements.autoReconnect.addEventListener("change", () => this.saveBrowserSettings());
    this.elements.reconnectAttempts.addEventListener("change", () => this.saveBrowserSettings());
    this.elements.reconnect.addEventListener("click", () => void this.runUiAction(() => this.reconnectNow()));
    this.elements.clipboardAutoSync.addEventListener("change", () => void this.runUiAction(async () => {
      this.saveBrowserSettings();
      await this.startClipboardPolling(true);
    }));
    this.elements.clipboardMaxKib.addEventListener("change", () => this.saveBrowserSettings());
    this.elements.clipboardCopyAndroid.addEventListener("click", () => void this.runUiAction(() => this.copyAndroidClipboard()));
    this.elements.settingsExport.addEventListener("click", () => this.exportSettings());
    this.elements.settingsImport.addEventListener("click", () => this.elements.settingsFile.click());
    this.elements.settingsFile.addEventListener("change", () => void this.runUiAction(() => this.importSettings()));
    document.addEventListener("keydown", (event) => {
      if (event.key === "F11") { event.preventDefault(); void this.toggleFullscreen(); }
    });
  }

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
    this.elements.imePolicy.disabled = this.elements.hideVirtualKeyboard.checked;
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
    const hasDevice = [...this.elements.device.options].some((option) => !option.disabled);
    const errors = validateDisplayForm(this.readDisplayValues());
    const unsupported = this.elements.displayMode.value === "virtual" && this.#capabilities?.virtualDisplaySupported === false;
    const selectedReady = [...this.elements.device.options].some((option) => option.value === this.elements.device.value && !option.disabled);
    const runtimeSerial = this.firstRuntime()?.serverSession.serial ?? null;
    const sameDevice = runtimeSerial === null || runtimeSerial === this.elements.device.value;
    const disabled = !hasDevice || !selectedReady || !sameDevice || errors.length > 0 || unsupported;
    this.elements.connect.disabled = disabled;
    this.elements.tabAdd.disabled = disabled;
  }

  private async refreshVirtualCapabilities(): Promise<void> {
    const serial = this.elements.device.value;
    if (!serial) {
      this.#capabilities = null;
      this.elements.capability.textContent = "Select an authorized device to probe virtual-display support.";
      return;
    }
    try {
      const [capabilities, apps] = await Promise.all([
        this.#api.virtualDisplayCapabilities(serial, this.elements.manualApp.value.trim() || "com.openai.chatgpt"),
        this.#api.launchableApps(serial),
      ]);
      this.#capabilities = capabilities;
      const localImeOption = [...this.elements.imePolicy.options].find((option) => option.value === "local");
      if (localImeOption) localImeOption.disabled = !capabilities.localImePolicySupported;
      if (!capabilities.localImePolicySupported && this.elements.imePolicy.value === "local") {
        this.elements.imePolicy.value = "default";
      }
      const previous = this.elements.virtualApp.value;
      this.elements.virtualApp.replaceChildren();
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "Manual package / no app";
      this.elements.virtualApp.append(empty);
      for (const app of apps.apps) {
        const option = document.createElement("option");
        option.value = app.packageName;
        option.textContent = `${app.label} · ${app.packageName}`;
        this.elements.virtualApp.append(option);
      }
      const desired = previous || this.elements.manualApp.value;
      if ([...this.elements.virtualApp.options].some((option) => option.value === desired)) this.elements.virtualApp.value = desired;
      const warningText = capabilities.warnings.length ? ` · ${capabilities.warnings.join(" ")}` : "";
      this.elements.capability.textContent = capabilities.virtualDisplaySupported
        ? `Supported · API ${capabilities.deviceApi} · codecs ${capabilities.supportedCodecs.join(", ")} · secondary-display input available${warningText}`
        : capabilities.warnings.join(" ");
      this.elements.capability.classList.toggle("error-text", !capabilities.virtualDisplaySupported);
    } catch (error) {
      this.#capabilities = null;
      this.elements.capability.textContent = `Capability probe failed: ${errorMessage(error)}. Physical Screen mode remains available.`;
      this.elements.capability.classList.add("error-text");
    }
    this.updateConnectAvailability();
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
    if (!this.#protocolSession || !this.#activeSessionId) return;
    const runtime = this.#runtimes.get(this.#activeSessionId);
    const canvas = event.currentTarget instanceof HTMLCanvasElement ? event.currentTarget : runtime?.canvas;
    if (!runtime || !canvas || canvas !== runtime.canvas) return;
    event.preventDefault();
    if (action === 0) {
      canvas.setPointerCapture(event.pointerId);
      canvas.focus();
    }
    const size = this.#renderer.screenSize;
    if (size.width <= 0 || size.height <= 0) return;
    const position = mapClientPoint(event.clientX, event.clientY, canvas.getBoundingClientRect(), size);
    await this.#protocolSession.sendControl({
      type: ControlMessageType.InjectTouchEvent,
      action,
      pointerId: BigInt(event.pointerId),
      position,
      pressure: action === 1 || action === 3 ? 0 : Math.max(0.01, event.pressure || 1),
      actionButton: 0,
      buttons: event.buttons,
    });
    if ((action === 1 || action === 3) && canvas.hasPointerCapture(event.pointerId)) {
      canvas.releasePointerCapture(event.pointerId);
    }
  }

  private async scroll(event: WheelEvent): Promise<void> {
    if (!this.#protocolSession || !this.#activeSessionId) return;
    const runtime = this.#runtimes.get(this.#activeSessionId);
    const canvas = event.currentTarget instanceof HTMLCanvasElement ? event.currentTarget : runtime?.canvas;
    if (!runtime || !canvas || canvas !== runtime.canvas) return;
    event.preventDefault();
    const size = this.#renderer.screenSize;
    if (size.width <= 0 || size.height <= 0) return;
    const position = mapClientPoint(event.clientX, event.clientY, canvas.getBoundingClientRect(), size);
    await this.#protocolSession.sendControl({
      type: ControlMessageType.InjectScrollEvent,
      position,
      horizontal: clamp(-event.deltaX / 80, -16, 16),
      vertical: clamp(-event.deltaY / 80, -16, 16),
      buttons: event.buttons,
    });
  }

  private async keydown(event: KeyboardEvent): Promise<void> {
    const shortcut = clipboardShortcut(event);
    if (shortcut === "paste") {
      event.preventDefault();
      await this.pasteClipboard("Ctrl+V");
      return;
    }
    if (shortcut === "copy") {
      event.preventDefault();
      this.#copyShortcutPending = true;
      await this.sendMessages([androidClipboardCopyMessage()]);
      return;
    }
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
    this.#powerOn = !this.#powerOn;
    await this.sendMessages([{ type: ControlMessageType.SetDisplayPower, on: this.#powerOn }]);
    this.elements.power.textContent = this.#powerOn ? "Screen off" : "Screen on";
  }

  private async pasteClipboard(source = "PC clipboard"): Promise<void> {
    if (!this.#protocolSession) return;
    let text = "";
    try {
      text = await navigator.clipboard.readText();
    } catch {
      text = this.elements.clipboardText.value;
      if (!text) throw new Error("Browser clipboard permission was denied. Paste text into the fallback box, then press Paste typed text.");
    }
    if (!text) text = this.elements.clipboardText.value;
    if (!text) throw new Error("The PC clipboard is empty. Click the Android input field first, then copy text or use the fallback box.");
    this.elements.clipboardText.value = text;
    await this.pasteText(text, source);
  }

  private async pasteTypedText(): Promise<void> {
    const text = this.elements.clipboardText.value;
    if (!text) throw new Error("Enter or paste text into the fallback box first");
    await this.pasteText(text, "typed text");
  }

  private async pasteText(text: string, source: string): Promise<void> {
    const session = this.#protocolSession;
    const maximum = Math.max(1, Math.min(256, Number(this.elements.clipboardMaxKib.value) || 256)) * 1024;
    if (new TextEncoder().encode(text).byteLength > maximum) throw new Error(`Clipboard text exceeds the configured ${maximum / 1024} KiB limit`);
    this.#lastSentClipboard = text;
    const runtime = this.#activeSessionId ? this.#runtimes.get(this.#activeSessionId) : null;
    if (runtime) runtime.lastSentClipboard = text;
    if (!session) return;
    const sequence = this.#clipboardSequence++;
    this.setStatus("Pasting", `Sending ${source} to the focused Android input field…`);
    const acknowledgement = this.waitForClipboardAcknowledgement(sequence);
    try {
      await session.sendControl(clipboardMessage(text, sequence, true));
      if (await acknowledgement) {
        this.setStatus("Clipboard pasted", `${source} was acknowledged by Android.`);
        return;
      }
      await this.sendMessages(textInjectionMessages(text));
      this.setStatus("Text fallback used", "Android did not acknowledge clipboard paste, so the text was injected directly.");
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

  private async consumeDeviceMessages(sessionId: string, session: ScrcpyV41Session): Promise<void> {
    while (this.#runtimes.get(sessionId)?.protocolSession === session) {
      const message = await session.readDeviceMessage();
      if (message.type === DeviceMessageType.AckClipboard) {
        this.resolveClipboardAcknowledgement(message.sequence, true);
        continue;
      }
      if (message.type !== DeviceMessageType.Clipboard) continue;
      const runtime = this.#runtimes.get(sessionId);
      if (!runtime) continue;
      runtime.lastAndroidClipboard = message.text;
      if (sessionId !== this.#activeSessionId) continue;

      const maximum = Math.max(1, Math.min(256, Number(this.elements.clipboardMaxKib.value) || 256)) * 1024;
      if (new TextEncoder().encode(message.text).byteLength > maximum) {
        this.setStatus("Clipboard skipped", `Android clipboard exceeds the configured ${maximum / 1024} KiB limit.`);
        continue;
      }
      this.#lastAndroidClipboard = message.text;
      this.elements.clipboardText.value = message.text;
      const copyShortcut = this.#copyShortcutPending;
      this.#copyShortcutPending = false;
      if (this.elements.clipboardAutoSync.checked || copyShortcut) {
        try {
          await navigator.clipboard.writeText(message.text);
          this.setStatus(copyShortcut ? "Clipboard copied" : "Clipboard synchronized", copyShortcut
            ? "Ctrl+C copied the Android selection to the PC clipboard."
            : "Android clipboard was copied to the PC clipboard.");
        } catch {
          this.setStatus("Clipboard received", "Android clipboard is available in the clipboard panel; browser write permission was unavailable.");
        }
      } else {
        this.setStatus("Clipboard received", "Android clipboard is available in the clipboard panel.");
      }
    }
  }

  private async handleRuntimeFailure(sessionId: string, error: unknown): Promise<void> {
    if (this.#closing || !this.#runtimes.has(sessionId)) return;
    const wasActive = sessionId === this.#activeSessionId;
    const message = errorMessage(error);
    await this.cleanupRuntime(sessionId);
    if (wasActive && !this.#serverSession) {
      this.setStatus("Stream stopped", message);
      if (!this.#manualDisconnect && this.elements.autoReconnect.checked) this.scheduleReconnect();
    }
  }

  private async cleanupSession(): Promise<void> {
    if (!this.#activeSessionId) return;
    await this.cleanupRuntime(this.#activeSessionId);
  }

  private async cleanupRuntime(sessionId: string): Promise<void> {
    const runtime = this.#runtimes.get(sessionId);
    if (!runtime) return;
    const wasActive = sessionId === this.#activeSessionId;
    if (wasActive) {
      this.stopFlexResize();
      this.stopClipboardPolling();
    }
    this.#runtimes.delete(sessionId);
    this.renderTabs();
    runtime.renderer.stop();
    runtime.audioPlayer.stop();
    runtime.lastAndroidClipboard = "";
    runtime.lastSentClipboard = "";
    if (wasActive) {
      this.#copyShortcutPending = false;
      for (const sequence of [...this.#clipboardAcks.keys()]) this.resolveClipboardAcknowledgement(sequence, false);
    }
    try {
      await runtime.protocolSession.close();
    } catch {
      await runtime.transport.close();
    }
    try {
      await this.#api.stopDeviceSession(runtime.serverSession.serial, sessionId);
    } catch {
      // A closing WebSocket may already have stopped this isolated server session.
    }
    this.releaseRuntimeCanvas(runtime.canvas);

    if (wasActive) {
      const next = this.#runtimes.values().next().value as DisplayRuntime | undefined;
      if (next) this.activateRuntime(next.serverSession.sessionId);
      else this.clearActiveRuntime();
    } else {
      this.renderTabs();
      this.updateConnectAvailability();
    }
  }

  private setConnectedControls(connected: boolean): void {
    this.elements.disconnect.disabled = !connected;
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
    this.elements.audioMute.disabled = !connected || !this.#protocolSession?.audioHeader;
    this.elements.audioVolume.disabled = !connected || !this.#protocolSession?.audioHeader;
    this.elements.device.disabled = this.#runtimes.size > 0;
    this.elements.reconnect.disabled = connected || !this.elements.device.value;
    this.updateDisplayUi();
    this.updateConnectAvailability();
  }

  private setBusy(busy: boolean): void {
    if (busy) {
      this.elements.connect.disabled = true;
      this.elements.tabAdd.disabled = true;
    }
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

  private updateRuntimeStatistics(sessionId: string | null, stats: VideoStatistics): void {
    if (!sessionId) return;
    const runtime = this.#runtimes.get(sessionId);
    if (!runtime) return;
    runtime.latestStatistics = stats;
    if (sessionId !== this.#activeSessionId) return;
    this.#latestStatistics = stats;
    this.showStatistics(stats);
    this.updateChannelStatus();
  }

  private showStatistics(stats: VideoStatistics): void {
    this.elements.statistics.textContent = `${stats.width}×${stats.height} · video decoded ${stats.framesDecoded} · dropped ${stats.framesDropped} · queue ${stats.decoderQueue} · sessions ${stats.sessionChanges + 1} · live tabs ${this.#runtimes.size}`;
  }

  private updateRuntimeAudioStatistics(sessionId: string | null, stats: AudioStatistics): void {
    if (!sessionId) return;
    const runtime = this.#runtimes.get(sessionId);
    if (!runtime) return;
    runtime.latestAudioStatistics = stats;
    if (sessionId !== this.#activeSessionId) return;
    this.#latestAudioStatistics = stats;
    this.showAudioStatistics(stats);
    this.updateChannelStatus();
  }

  private showAudioStatistics(stats: AudioStatistics): void {
    this.elements.audioStatus.textContent = `${stats.codec} · ${stats.packetsDecoded} packets · ${stats.bufferedMilliseconds} ms buffered${stats.muted ? " · muted" : ""}`;
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
    const runtime = this.#activeSessionId ? this.#runtimes.get(this.#activeSessionId) : null;
    const text = runtime?.lastAndroidClipboard ?? this.#lastAndroidClipboard;
    if (!text) throw new Error("No Android clipboard text has been received yet");
    await navigator.clipboard.writeText(text);
    this.setStatus("Clipboard copied", "Android clipboard was copied to the PC clipboard.");
  }

  private async startClipboardPolling(requestPermission: boolean): Promise<void> {
    this.stopClipboardPolling();
    this.#clipboardReadAllowed = false;
    if (!this.#protocolSession || !this.elements.clipboardAutoSync.checked) return;

    if (!navigator.clipboard?.readText) {
      this.setStatus("Clipboard sync limited", "This browser cannot read the PC clipboard automatically. Android → PC synchronization remains available.");
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
      this.setStatus("Clipboard sync limited", "Automatic PC → Android clipboard access is blocked by the browser. Use Paste manually; Android → PC sync remains active.");
      return;
    }
    if (permissionState !== "granted" && !requestPermission) {
      // Never let a background timer trigger repeated permission/paste prompts. A single
      // checkbox gesture can explicitly arm PC → Android synchronization when desired.
      this.setStatus("Clipboard sync ready", "Android → PC sync is active. Toggle automatic sync off/on once to grant PC → Android clipboard access.");
      return;
    }

    try {
      // This read is either already permission-granted or is called directly from the user's
      // checkbox gesture. It is the only place allowed to request clipboard-read permission.
      const initial = await navigator.clipboard.readText();
      this.#clipboardReadAllowed = true;
      if (initial && initial !== this.#lastSentClipboard && initial !== this.#lastAndroidClipboard) {
        await this.synchronizePcClipboard(initial);
      }
      this.#clipboardPollTimer = window.setInterval(() => void this.pollPcClipboard(), 1800);
    } catch {
      this.#clipboardReadAllowed = false;
      this.setStatus("Clipboard sync limited", "Browser clipboard permission was not granted. Use Paste manually; Android → PC synchronization remains active.");
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
    this.#lastSentClipboard = text;
    const runtime = this.#activeSessionId ? this.#runtimes.get(this.#activeSessionId) : null;
    if (runtime) runtime.lastSentClipboard = text;
    const sequence = this.#clipboardSequence++;
    // Automatic synchronization updates Android's clipboard only.  It MUST NOT
    // request a paste action, because repeated paste=true messages steal focus
    // from the Android input method and make normal PC keyboard typing unusable.
    await session.sendControl(clipboardMessage(text, sequence, false));
    this.setStatus("Clipboard synchronized", "PC clipboard was updated on Android without pasting into the focused field.");
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
    this.elements.settingsStatus.textContent = "Settings imported. Reconnect to apply session options.";
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
