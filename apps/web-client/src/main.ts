import { inspectBrowserCapabilities } from "./browser-support.js";
import { DroidWebDisplayController } from "./controller.js";
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
      file: required<HTMLInputElement>("#upload-file"),
      contextUploadFile: required<HTMLInputElement>("#context-upload-file"),
      uploadDirectory: required<HTMLSelectElement>("#upload-directory"),
      duplicatePolicy: required<HTMLSelectElement>("#duplicate-policy"),
      upload: required<HTMLButtonElement>("#upload-file-button"),
      openUploadFolder: required<HTMLButtonElement>("#open-upload-folder"),
      storageRoot: required<HTMLSelectElement>("#storage-root"),
      storagePath: required<HTMLInputElement>("#storage-path"),
      storageBreadcrumbs: required<HTMLElement>("#storage-breadcrumbs"),
      storageUp: required<HTMLButtonElement>("#storage-up"),
      storageRefresh: required<HTMLButtonElement>("#storage-refresh"),
      storageSelectAll: required<HTMLInputElement>("#storage-select-all"),
      storageBody: required<HTMLElement>("#storage-body"),
      contextMenu: required<HTMLElement>("#storage-context-menu"),
      contextOpen: required<HTMLButtonElement>("#context-open"),
      contextDownload: required<HTMLButtonElement>("#context-download"),
      contextUpload: required<HTMLButtonElement>("#context-upload"),
      contextRefresh: required<HTMLButtonElement>("#context-refresh"),
      destinationProfile: required<HTMLSelectElement>("#destination-profile"),
      downloadSelected: required<HTMLButtonElement>("#download-selected"),
      openPcFolder: required<HTMLButtonElement>("#open-pc-folder"),
      transferList: required<HTMLElement>("#transfer-list"),
      transferStatus: required<HTMLElement>("#transfer-status"),
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
    window.addEventListener("beforeunload", () => { controller.stopOnUnload(); runningAppController.close(); });
    void controller.initialize()
      .then(() => Promise.all([transferController.initialize(), autoDownloadController.initialize(), runningAppController.initialize()]))
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
