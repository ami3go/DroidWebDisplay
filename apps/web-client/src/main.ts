import { inspectBrowserCapabilities } from "./browser-support.js";
import { DroidWebDisplayController } from "./controller.js";
import { CLIPBOARD_STATUS } from "./clipboard-status.js";
import { clipboardShortcut, isEditableTarget } from "./input.js";
import { AutoDownloadController } from "./auto-download-controller.js";
import { TransferController } from "./transfer-controller.js";
import { RunningAppController } from "./running-app-controller.js";
import { AuthController } from "./auth-controller.js";
import { NetworkAccessController } from "./network-controller.js";

function required<T extends Element>(selector: string): T {
  const value = document.querySelector<T>(selector);
  if (!value) throw new Error(`Missing UI element: ${selector}`);
  return value;
}

function bindAndroidCopyWriteThrough(): void {
  const button = required<HTMLButtonElement>("#clipboard-copy-android");
  const canvas = required<HTMLCanvasElement>("#screen");
  const clipboardText = required<HTMLTextAreaElement>("#clipboard-text");
  const status = required<HTMLElement>("#status");
  const details = required<HTMLElement>("#details");
  const statusContainer = required<HTMLElement>("#connection-status");
  let generation = 0;

  /** Mirror the side effects of controller.setStatus for the fields that describe
      the status line itself. data-state is deliberately untouched: a copy does
      not change the connection state, but title and aria-label describe the
      visible text and go stale if only textContent is written. */
  const writeStatus = (headline: string, detail: string): void => {
    status.textContent = headline;
    details.textContent = detail;
    statusContainer.title = detail;
    statusContainer.setAttribute("aria-label", `${statusContainer.dataset.state ?? "unknown"}: ${headline}. ${detail}`);
  };

  const finishCopy = async (): Promise<void> => {
    // Ctrl+C reaches this listener anywhere outside editable/selected PC text,
    // including with no device attached. The controller suppresses its own
    // "not confirmed" message in that case, so claiming a failed copy here
    // would reinstate the very message it takes care to avoid.
    if (statusContainer.dataset.state !== "connected") return;

    const request = ++generation;
    const initialText = clipboardText.value;
    const initialStatus = status.textContent?.trim() ?? "";
    const deadline = performance.now() + 1200;
    let responseObserved = false;

    while (performance.now() < deadline) {
      if (request !== generation) return;
      const currentStatus = status.textContent?.trim() ?? "";
      const textChanged = clipboardText.value !== initialText;
      const statusChanged = currentStatus !== initialStatus;
      if (statusChanged && currentStatus === CLIPBOARD_STATUS.notConfirmed) return;
      if ((textChanged || statusChanged) && currentStatus === CLIPBOARD_STATUS.copied) return;
      if (textChanged || (statusChanged && currentStatus === CLIPBOARD_STATUS.received)) {
        responseObserved = true;
        break;
      }
      await new Promise<void>((resolve) => window.setTimeout(resolve, 20));
    }

    if (request !== generation) return;
    if (!responseObserved) {
      // Only claim "not confirmed" when nothing else has explained the silence.
      // A disconnect or an over-limit clipboard sets its own terminal status,
      // and overwriting it replaces an accurate diagnosis with a wrong one.
      const currentStatus = status.textContent?.trim() ?? "";
      if (currentStatus === initialStatus || currentStatus === CLIPBOARD_STATUS.copying) {
        writeStatus(CLIPBOARD_STATUS.notConfirmed, "Android did not return a new clipboard value. The previous PC clipboard was left unchanged.");
      }
      return;
    }
    const text = clipboardText.value;
    if (!text) {
      writeStatus(CLIPBOARD_STATUS.notConfirmed, "Android did not return clipboard text.");
      return;
    }

    try {
      await navigator.clipboard.writeText(text);
      if (request !== generation) return;
      writeStatus(CLIPBOARD_STATUS.copied, "Android selection was copied to the PC clipboard.");
      return;
    } catch {
      // Every other exit re-checks the generation; without it here a superseded
      // copy still yanks focus and writes its result over the newer request.
      if (request !== generation) return;
      // execCommand copies the live selection, so it can only be trusted while
      // the textarea still holds the text this request validated.
      if (clipboardText.value !== text) return;
      const selectionStart = clipboardText.selectionStart;
      const selectionEnd = clipboardText.selectionEnd;
      const previouslyFocused = document.activeElement;
      clipboardText.focus();
      clipboardText.select();
      const copied = document.execCommand("copy");
      clipboardText.setSelectionRange(selectionStart, selectionEnd);
      // Restore where focus actually was rather than assuming the canvas: this
      // path runs on every copy in browsers without the async Clipboard API, and
      // parking focus on the canvas sends the next keystroke to Android.
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
      else canvas.focus();
      if (request !== generation) return;
      if (copied) {
        writeStatus(CLIPBOARD_STATUS.copied, "Android selection was copied to the PC clipboard using the browser fallback.");
      } else {
        writeStatus(CLIPBOARD_STATUS.received, "Android clipboard reached the browser, but the browser blocked writing to the PC clipboard.");
      }
    }
  };

  button.addEventListener("click", () => void finishCopy());
  document.addEventListener("keydown", (event) => {
    // Reuse the controller's predicate instead of restating it: a copy of this
    // condition drifts out of step with the keydown handler it shadows.
    const selection = document.getSelection();
    if (
      event.repeat
      || isEditableTarget(event.target)
      || (selection !== null && !selection.isCollapsed)
      || clipboardShortcut(event) !== "copy"
    ) return;
    void finishCopy();
  });
}

function browserGpuRenderer(): string {
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl");
    if (!gl) return "WebGL unavailable";
    const debug = gl.getExtension("WEBGL_debug_renderer_info") as { readonly UNMASKED_RENDERER_WEBGL: number } | null;
    const value = gl.getParameter(debug?.UNMASKED_RENDERER_WEBGL ?? gl.RENDERER);
    return typeof value === "string" && value.trim() ? value.trim() : "WebGL available";
  } catch {
    return "GPU renderer unavailable";
  }
}

function installBrowserDiagnostics(capabilities: ReturnType<typeof inspectBrowserCapabilities>): void {
  const statistics = required<HTMLElement>("#statistics");
  const gpu = browserGpuRenderer();
  const webCodecs = capabilities.supported ? "WebCodecs ready" : `missing ${capabilities.missing.join(", ")}`;
  const cpu = capabilities.hardwareConcurrency === null ? "CPU ?" : `${capabilities.hardwareConcurrency} logical CPU`;
  const summary = `${capabilities.browserName} · ${capabilities.platform} · ${webCodecs} · ${cpu} · GPU ${gpu}`;
  statistics.textContent = summary;
  statistics.dataset.browserDiagnostics = summary;
  statistics.title = `${summary}. If controls work but video is black: update Chrome/Edge and the GPU driver; if needed disable browser hardware acceleration, restart the browser, then reconnect.`;
}

function bindAdbDeviceGuidance(): void {
  const device = required<HTMLSelectElement>("#device");
  const status = required<HTMLElement>("#status");
  const details = required<HTMLElement>("#details");
  const statusContainer = required<HTMLElement>("#connection-status");
  const guidanceTitles = new Set([
    "USB authorization required",
    "ADB device offline",
    "ADB access blocked",
    "No Android device",
    "ADB device not ready",
  ]);

  const update = (): void => {
    const options = [...device.options];
    if (options.some((option) => Boolean(option.value) && !option.disabled)) {
      if (guidanceTitles.has(status.textContent?.trim() ?? "")) {
        status.textContent = "Ready";
        details.textContent = "An authorized Android device is available. Select it and connect.";
        statusContainer.setAttribute("aria-label", "disconnected: Ready. An authorized Android device is available.");
      }
      return;
    }

    const labels = options.map((option) => option.textContent?.toLowerCase() ?? "").join(" ");
    if (labels.includes("unauthorized") || labels.includes("authorizing")) {
      status.textContent = "USB authorization required";
      details.textContent = "Unlock the Android device, accept “Allow USB debugging?”, then refresh devices.";
    } else if (labels.includes("no permissions")) {
      status.textContent = "ADB access blocked";
      details.textContent = "The phone is visible but ADB cannot access it. On Windows, install/update the phone OEM USB driver and reconnect USB.";
    } else if (labels.includes("offline")) {
      status.textContent = "ADB device offline";
      details.textContent = "Reconnect USB, unlock the phone, and toggle USB debugging if the device remains offline.";
    } else if (!options.length) {
      status.textContent = "No Android device";
      details.textContent = "Connect the phone with USB debugging enabled. Windows may require the manufacturer/OEM USB driver.";
    } else {
      status.textContent = "ADB device not ready";
      details.textContent = `Connected device state: ${options[0]?.textContent?.trim() || "unknown"}. Resolve the USB/Android state and refresh devices.`;
    }
    statusContainer.setAttribute("aria-label", `disconnected: ${status.textContent}. ${details.textContent}`);
  };

  new MutationObserver(update).observe(device, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
  device.addEventListener("change", update);
  update();
}

async function bootstrap(): Promise<void> {
  const auth = new AuthController({
    gate: required<HTMLElement>("#auth-gate"),
    form: required<HTMLFormElement>("#auth-form"),
    title: required<HTMLElement>("#auth-title"),
    explanation: required<HTMLElement>("#auth-explanation"),
    pin: required<HTMLInputElement>("#auth-pin"),
    confirmRow: required<HTMLElement>("#auth-confirm-row"),
    confirmPin: required<HTMLInputElement>("#auth-confirm-pin"),
    duration: required<HTMLSelectElement>("#auth-duration"),
    customRow: required<HTMLElement>("#auth-custom-row"),
    customValue: required<HTMLInputElement>("#auth-custom-value"),
    customUnit: required<HTMLSelectElement>("#auth-custom-unit"),
    label: required<HTMLInputElement>("#auth-label"),
    error: required<HTMLElement>("#auth-error"),
    submit: required<HTMLButtonElement>("#auth-submit"),
    securityCard: required<HTMLElement>("#security-card"),
    sessionSummary: required<HTMLElement>("#auth-session-summary"),
    sessionList: required<HTMLElement>("#auth-session-list"),
    refreshSessions: required<HTMLButtonElement>("#auth-refresh-sessions"),
    logout: required<HTMLButtonElement>("#auth-logout"),
    currentPin: required<HTMLInputElement>("#auth-current-pin"),
    newPin: required<HTMLInputElement>("#auth-new-pin"),
    confirmNewPin: required<HTMLInputElement>("#auth-confirm-new-pin"),
    changePin: required<HTMLButtonElement>("#auth-change-pin"),
    revokeAllPin: required<HTMLInputElement>("#auth-revoke-all-pin"),
    revokeAll: required<HTMLButtonElement>("#auth-revoke-all"),
    securityStatus: required<HTMLElement>("#auth-security-status"),
  });
  await auth.ensureAuthenticated();
  const capabilities = inspectBrowserCapabilities();
  const unsupported = required<HTMLElement>("#unsupported");
  const app = required<HTMLElement>("#app");

  if (!capabilities.supported) {
    unsupported.hidden = false;
    unsupported.textContent = `This browser is unsupported. Missing: ${capabilities.missing.join(", ")}. Use a current Chromium browser with WebCodecs.`;
  } else {
    app.hidden = false;
    installBrowserDiagnostics(capabilities);
    const networkController = new NetworkAccessController({
      card: required<HTMLElement>("#network-card"),
      badge: required<HTMLElement>("#network-mode-badge"),
      warning: required<HTMLElement>("#network-warning"),
      mode: required<HTMLSelectElement>("#network-mode"),
      lanFields: required<HTMLElement>("#network-lan-fields"),
      interfaceSelect: required<HTMLSelectElement>("#network-interface"),
      bindAddress: required<HTMLInputElement>("#network-bind-address"),
      allowedNetworks: required<HTMLInputElement>("#network-allowed-networks"),
      hostname: required<HTMLInputElement>("#network-hostname"),
      certificateSource: required<HTMLSelectElement>("#network-certificate-source"),
      existingCertificate: required<HTMLElement>("#network-existing-certificate"),
      certificatePath: required<HTMLInputElement>("#network-certificate-path"),
      privateKeyPath: required<HTMLInputElement>("#network-private-key-path"),
      validityRow: required<HTMLElement>("#network-validity-row"),
      certificateValidity: required<HTMLSelectElement>("#network-certificate-validity"),
      manageFirewall: required<HTMLInputElement>("#network-manage-firewall"),
      port: required<HTMLInputElement>("#network-port"),
      currentPin: required<HTMLInputElement>("#network-current-pin"),
      validate: required<HTMLButtonElement>("#network-validate"),
      apply: required<HTMLButtonElement>("#network-apply"),
      disable: required<HTMLButtonElement>("#network-disable"),
      copyUrl: required<HTMLButtonElement>("#network-copy-url"),
      downloadCertificate: required<HTMLAnchorElement>("#network-download-certificate"),
      url: required<HTMLElement>("#network-url"),
      status: required<HTMLElement>("#network-status"),
    });
    await networkController.initialize();

    const audioToggle = required<HTMLInputElement>("#audio-enabled");
    const audioStatus = required<HTMLElement>("#audio-status");
    if (!capabilities.audioSupported) {
      audioToggle.checked = false;
      audioToggle.disabled = true;
      audioStatus.textContent = `Audio unsupported by this browser. Missing: ${capabilities.missingAudio.join(", ")}.`;
    }
    const controller = new DroidWebDisplayController({
      device: required<HTMLSelectElement>("#device"),
      connect: required<HTMLButtonElement>("#connect"),
      canvas: required<HTMLCanvasElement>("#screen"),
      stage: required<HTMLElement>("#stage"),
      statusContainer: required<HTMLElement>("#connection-status"),
      statusIcon: required<HTMLElement>("#status-icon"),
      status: required<HTMLElement>("#status"),
      details: required<HTMLElement>("#details"),
      statistics: required<HTMLElement>("#statistics"),
      back: required<HTMLButtonElement>("#back"),
      home: required<HTMLButtonElement>("#home"),
      recent: required<HTMLButtonElement>("#recent"),
      rotate: required<HTMLButtonElement>("#rotate"),
      power: required<HTMLButtonElement>("#power"),
      clipboard: required<HTMLButtonElement>("#clipboard"),
      clipboardText: required<HTMLTextAreaElement>("#clipboard-text"),
      clipboardTextPaste: required<HTMLButtonElement>("#clipboard-text-paste"),
      fullscreen: required<HTMLButtonElement>("#fullscreen"),
      audioEnabled: audioToggle,
      audioMute: required<HTMLButtonElement>("#audio-mute"),
      audioVolume: required<HTMLInputElement>("#audio-volume"),
      audioStatus,
      autoReconnect: required<HTMLInputElement>("#auto-reconnect"),
      reconnectAttempts: required<HTMLSelectElement>("#reconnect-attempts"),
      reconnect: required<HTMLButtonElement>("#reconnect"),
      sessionChannels: required<HTMLElement>("#session-channels"),
      clipboardAutoSync: required<HTMLInputElement>("#clipboard-auto-sync"),
      clipboardMaxKib: required<HTMLInputElement>("#clipboard-max-kib"),
      clipboardCopyAndroid: required<HTMLButtonElement>("#clipboard-copy-android"),
      settingsExport: required<HTMLButtonElement>("#settings-export"),
      settingsImport: required<HTMLButtonElement>("#settings-import"),
      settingsFile: required<HTMLInputElement>("#settings-file"),
      settingsStatus: required<HTMLElement>("#settings-status"),
      quickAppConfigure: required<HTMLButtonElement>("#quick-app-configure"),
      quickAppHeader: required<HTMLElement>("#quick-app-header"),
      quickAppAdd: required<HTMLButtonElement>("#quick-app-add"),
      quickAppList: required<HTMLElement>("#quick-app-list"),
      quickAppSettingsStatus: required<HTMLElement>("#quick-app-settings-status"),
      displayMode: required<HTMLSelectElement>("#display-mode"),
      displayProfile: required<HTMLSelectElement>("#display-profile"),
      virtualSettings: required<HTMLElement>("#virtual-display-settings"),
      sizeMode: required<HTMLSelectElement>("#virtual-size-mode"),
      virtualWidth: required<HTMLInputElement>("#virtual-width"),
      virtualHeight: required<HTMLInputElement>("#virtual-height"),
      virtualDpi: required<HTMLInputElement>("#virtual-dpi"),
      virtualApp: required<HTMLSelectElement>("#virtual-app"),
      manualApp: required<HTMLInputElement>("#virtual-app-package"),
      forceStop: required<HTMLInputElement>("#virtual-force-stop"),
      keepActive: required<HTMLInputElement>("#virtual-keep-active"),
      systemDecorations: required<HTMLInputElement>("#virtual-system-decorations"),
      destroyContent: required<HTMLInputElement>("#virtual-destroy-content"),
      imePolicy: required<HTMLSelectElement>("#virtual-ime-policy"),
      hideVirtualKeyboard: required<HTMLInputElement>("#virtual-hide-keyboard"),
      preserveAspect: required<HTMLInputElement>("#virtual-preserve-aspect"),
      videoBitrate: required<HTMLInputElement>("#virtual-bitrate"),
      virtualMaxFps: required<HTMLInputElement>("#virtual-max-fps"),
      displaySummary: required<HTMLElement>("#display-summary"),
      capability: required<HTMLElement>("#virtual-capability"),
    });
    bindAndroidCopyWriteThrough();
    const runningAppController = new RunningAppController({
      device: required<HTMLSelectElement>("#device"),
      select: required<HTMLSelectElement>("#running-app-select"),
      icon: required<HTMLButtonElement>("#running-app-icon"),
      count: required<HTMLElement>("#running-app-count"),
      status: required<HTMLElement>("#running-app-status"),
      diagnosticDisplay: required<HTMLElement>("#diagnostic-display"),
      diagnosticRam: required<HTMLElement>("#diagnostic-ram"),
    });
    const transferController = new TransferController({
      device: required<HTMLSelectElement>("#device"),
      contextUploadFile: required<HTMLInputElement>("#context-upload-file"),
      customDestinationRow: required<HTMLElement>("#custom-destination-row"),
      customDestinationPath: required<HTMLInputElement>("#custom-destination-path"),
      duplicatePolicy: required<HTMLSelectElement>("#duplicate-policy"),
      fileBrowserTab: required<HTMLButtonElement>("#file-browser-tab"),
      recentPicturesTab: required<HTMLButtonElement>("#recent-pictures-tab"),
      fileBrowserControls: required<HTMLElement>("#file-browser-controls"),
      recentPicturesControls: required<HTMLElement>("#recent-pictures-controls"),
      recentPicturesRefresh: required<HTMLButtonElement>("#recent-pictures-refresh"),
      storageRoot: required<HTMLSelectElement>("#storage-root"),
      storagePath: required<HTMLInputElement>("#storage-path"),
      storageBreadcrumbs: required<HTMLElement>("#storage-breadcrumbs"),
      storageUp: required<HTMLButtonElement>("#storage-up"),
      storageRefresh: required<HTMLButtonElement>("#storage-refresh"),
      storageSelectAll: required<HTMLInputElement>("#storage-select-all"),
      storageBody: required<HTMLElement>("#storage-body"),
      explorerFrame: required<HTMLElement>("#explorer-frame"),
      explorerHelp: required<HTMLElement>("#explorer-help"),
      contextMenu: required<HTMLElement>("#storage-context-menu"),
      contextOpen: required<HTMLButtonElement>("#context-open"),
      contextDownload: required<HTMLButtonElement>("#context-download"),
      contextUpload: required<HTMLButtonElement>("#context-upload"),
      contextDelete: required<HTMLButtonElement>("#context-delete"),
      contextRefresh: required<HTMLButtonElement>("#context-refresh"),
      destinationProfile: required<HTMLSelectElement>("#destination-profile"),
      downloadSelected: required<HTMLButtonElement>("#download-selected"),
      openPcFolder: required<HTMLButtonElement>("#open-pc-folder"),
      transferList: required<HTMLElement>("#transfer-list"),
      transferStatus: required<HTMLElement>("#transfer-status"),
      stage: required<HTMLElement>("#stage"),
      stageDropOverlay: required<HTMLElement>("#stage-drop-overlay"),
    });
    const autoDownloadController = new AutoDownloadController({
      device: required<HTMLSelectElement>("#device"),
      enabled: required<HTMLInputElement>("#auto-download-enabled"),
      pcToAndroidEnabled: required<HTMLInputElement>("#auto-upload-enabled"),
      source: required<HTMLSelectElement>("#auto-download-source"),
      destination: required<HTMLSelectElement>("#auto-download-destination"),
      uploadDuplicatePolicy: required<HTMLSelectElement>("#auto-upload-duplicate"),
      scanInterval: required<HTMLInputElement>("#auto-download-scan"),
      stabilitySeconds: required<HTMLInputElement>("#auto-download-stability"),
      stabilityObservations: required<HTMLInputElement>("#auto-download-observations"),
      includeExisting: required<HTMLInputElement>("#auto-download-existing"),
      includeExistingPc: required<HTMLInputElement>("#auto-upload-existing"),
      deleteAfterVerified: required<HTMLInputElement>("#auto-download-delete"),
      notifications: required<HTMLInputElement>("#auto-download-notifications"),
      save: required<HTMLButtonElement>("#auto-download-save"),
      scanNow: required<HTMLButtonElement>("#auto-download-scan-now"),
      reset: required<HTMLButtonElement>("#auto-download-reset"),
      status: required<HTMLElement>("#auto-download-status"),
      summary: required<HTMLElement>("#auto-download-summary"),
      events: required<HTMLElement>("#auto-download-events"),
    });
    window.addEventListener("beforeunload", () => { controller.stopOnUnload(); runningAppController.close(); transferController.close(); autoDownloadController.close(); });
    void controller.initialize()
      .then(() => {
        bindAdbDeviceGuidance();
        return Promise.all([transferController.initialize(), autoDownloadController.initialize(), runningAppController.initialize()]);
      })
      .catch((error: unknown) => {
      required<HTMLElement>("#status").textContent = "Initialization failed";
      required<HTMLElement>("#details").textContent = error instanceof Error ? error.message : String(error);
    });
  }
}

void bootstrap().catch((error: unknown) => {
  const gateError = document.querySelector<HTMLElement>("#auth-error");
  if (gateError) gateError.textContent = error instanceof Error ? error.message : String(error);
});
