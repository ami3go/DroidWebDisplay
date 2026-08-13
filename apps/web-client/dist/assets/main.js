import { inspectBrowserCapabilities } from "./browser-support.js";
import { DroidWebDisplayController } from "./controller.js";
import { AutoDownloadController } from "./auto-download-controller.js";
import { TransferController } from "./transfer-controller.js";
import { RunningAppController } from "./running-app-controller.js";
import { AuthController } from "./auth-controller.js";
import { NetworkAccessController } from "./network-controller.js";
function required(selector) {
    const value = document.querySelector(selector);
    if (!value)
        throw new Error(`Missing UI element: ${selector}`);
    return value;
}
async function bootstrap() {
    const auth = new AuthController({
        gate: required("#auth-gate"),
        form: required("#auth-form"),
        title: required("#auth-title"),
        explanation: required("#auth-explanation"),
        pin: required("#auth-pin"),
        confirmRow: required("#auth-confirm-row"),
        confirmPin: required("#auth-confirm-pin"),
        duration: required("#auth-duration"),
        customRow: required("#auth-custom-row"),
        customValue: required("#auth-custom-value"),
        customUnit: required("#auth-custom-unit"),
        label: required("#auth-label"),
        error: required("#auth-error"),
        submit: required("#auth-submit"),
        securityCard: required("#security-card"),
        sessionSummary: required("#auth-session-summary"),
        sessionList: required("#auth-session-list"),
        refreshSessions: required("#auth-refresh-sessions"),
        logout: required("#auth-logout"),
        currentPin: required("#auth-current-pin"),
        newPin: required("#auth-new-pin"),
        confirmNewPin: required("#auth-confirm-new-pin"),
        changePin: required("#auth-change-pin"),
        revokeAllPin: required("#auth-revoke-all-pin"),
        revokeAll: required("#auth-revoke-all"),
        securityStatus: required("#auth-security-status"),
    });
    await auth.ensureAuthenticated();
    const capabilities = inspectBrowserCapabilities();
    const unsupported = required("#unsupported");
    const app = required("#app");
    if (!capabilities.supported) {
        unsupported.hidden = false;
        unsupported.textContent = `This browser is unsupported. Missing: ${capabilities.missing.join(", ")}. Use a current Chromium browser with WebCodecs.`;
    }
    else {
        app.hidden = false;
        const networkController = new NetworkAccessController({
            card: required("#network-card"),
            badge: required("#network-mode-badge"),
            warning: required("#network-warning"),
            mode: required("#network-mode"),
            lanFields: required("#network-lan-fields"),
            interfaceSelect: required("#network-interface"),
            bindAddress: required("#network-bind-address"),
            allowedNetworks: required("#network-allowed-networks"),
            hostname: required("#network-hostname"),
            certificateSource: required("#network-certificate-source"),
            existingCertificate: required("#network-existing-certificate"),
            certificatePath: required("#network-certificate-path"),
            privateKeyPath: required("#network-private-key-path"),
            validityRow: required("#network-validity-row"),
            certificateValidity: required("#network-certificate-validity"),
            manageFirewall: required("#network-manage-firewall"),
            port: required("#network-port"),
            currentPin: required("#network-current-pin"),
            validate: required("#network-validate"),
            apply: required("#network-apply"),
            disable: required("#network-disable"),
            copyUrl: required("#network-copy-url"),
            downloadCertificate: required("#network-download-certificate"),
            url: required("#network-url"),
            status: required("#network-status"),
        });
        await networkController.initialize();
        const audioToggle = required("#audio-enabled");
        const audioStatus = required("#audio-status");
        if (!capabilities.audioSupported) {
            audioToggle.checked = false;
            audioToggle.disabled = true;
            audioStatus.textContent = `Audio unsupported by this browser. Missing: ${capabilities.missingAudio.join(", ")}.`;
        }
        const controller = new DroidWebDisplayController({
            device: required("#device"),
            connect: required("#connect"),
            canvas: required("#screen"),
            stage: required("#stage"),
            statusContainer: required("#connection-status"),
            statusIcon: required("#status-icon"),
            status: required("#status"),
            details: required("#details"),
            statistics: required("#statistics"),
            back: required("#back"),
            home: required("#home"),
            recent: required("#recent"),
            rotate: required("#rotate"),
            power: required("#power"),
            clipboard: required("#clipboard"),
            clipboardText: required("#clipboard-text"),
            clipboardTextPaste: required("#clipboard-text-paste"),
            fullscreen: required("#fullscreen"),
            audioEnabled: audioToggle,
            audioMute: required("#audio-mute"),
            audioVolume: required("#audio-volume"),
            audioStatus,
            autoReconnect: required("#auto-reconnect"),
            reconnectAttempts: required("#reconnect-attempts"),
            reconnect: required("#reconnect"),
            sessionChannels: required("#session-channels"),
            clipboardAutoSync: required("#clipboard-auto-sync"),
            clipboardMaxKib: required("#clipboard-max-kib"),
            clipboardCopyAndroid: required("#clipboard-copy-android"),
            settingsExport: required("#settings-export"),
            settingsImport: required("#settings-import"),
            settingsFile: required("#settings-file"),
            settingsStatus: required("#settings-status"),
            displayMode: required("#display-mode"),
            displayProfile: required("#display-profile"),
            virtualSettings: required("#virtual-display-settings"),
            sizeMode: required("#virtual-size-mode"),
            virtualWidth: required("#virtual-width"),
            virtualHeight: required("#virtual-height"),
            virtualDpi: required("#virtual-dpi"),
            virtualApp: required("#virtual-app"),
            manualApp: required("#virtual-app-package"),
            forceStop: required("#virtual-force-stop"),
            keepActive: required("#virtual-keep-active"),
            systemDecorations: required("#virtual-system-decorations"),
            destroyContent: required("#virtual-destroy-content"),
            imePolicy: required("#virtual-ime-policy"),
            hideVirtualKeyboard: required("#virtual-hide-keyboard"),
            preserveAspect: required("#virtual-preserve-aspect"),
            videoBitrate: required("#virtual-bitrate"),
            virtualMaxFps: required("#virtual-max-fps"),
            displaySummary: required("#display-summary"),
            capability: required("#virtual-capability"),
        });
        const runningAppController = new RunningAppController({
            device: required("#device"),
            select: required("#running-app-select"),
            icon: required("#running-app-icon"),
            count: required("#running-app-count"),
            status: required("#running-app-status"),
            diagnosticDisplay: required("#diagnostic-display"),
            diagnosticRam: required("#diagnostic-ram"),
        });
        const transferController = new TransferController({
            device: required("#device"),
            file: required("#upload-file"),
            contextUploadFile: required("#context-upload-file"),
            uploadDirectory: required("#upload-directory"),
            duplicatePolicy: required("#duplicate-policy"),
            upload: required("#upload-file-button"),
            openUploadFolder: required("#open-upload-folder"),
            storageRoot: required("#storage-root"),
            storagePath: required("#storage-path"),
            storageBreadcrumbs: required("#storage-breadcrumbs"),
            storageUp: required("#storage-up"),
            storageRefresh: required("#storage-refresh"),
            storageSelectAll: required("#storage-select-all"),
            storageBody: required("#storage-body"),
            contextMenu: required("#storage-context-menu"),
            contextOpen: required("#context-open"),
            contextDownload: required("#context-download"),
            contextUpload: required("#context-upload"),
            contextRefresh: required("#context-refresh"),
            destinationProfile: required("#destination-profile"),
            downloadSelected: required("#download-selected"),
            openPcFolder: required("#open-pc-folder"),
            transferList: required("#transfer-list"),
            transferStatus: required("#transfer-status"),
        });
        const autoDownloadController = new AutoDownloadController({
            device: required("#device"),
            enabled: required("#auto-download-enabled"),
            pcToAndroidEnabled: required("#auto-upload-enabled"),
            source: required("#auto-download-source"),
            destination: required("#auto-download-destination"),
            uploadDuplicatePolicy: required("#auto-upload-duplicate"),
            scanInterval: required("#auto-download-scan"),
            stabilitySeconds: required("#auto-download-stability"),
            stabilityObservations: required("#auto-download-observations"),
            includeExisting: required("#auto-download-existing"),
            includeExistingPc: required("#auto-upload-existing"),
            deleteAfterVerified: required("#auto-download-delete"),
            notifications: required("#auto-download-notifications"),
            save: required("#auto-download-save"),
            scanNow: required("#auto-download-scan-now"),
            reset: required("#auto-download-reset"),
            status: required("#auto-download-status"),
            summary: required("#auto-download-summary"),
            events: required("#auto-download-events"),
        });
        window.addEventListener("beforeunload", () => { controller.stopOnUnload(); runningAppController.close(); });
        void controller.initialize()
            .then(() => Promise.all([transferController.initialize(), autoDownloadController.initialize(), runningAppController.initialize()]))
            .catch((error) => {
            required("#status").textContent = "Initialization failed";
            required("#details").textContent = error instanceof Error ? error.message : String(error);
        });
    }
}
void bootstrap().catch((error) => {
    const gateError = document.querySelector("#auth-error");
    if (gateError)
        gateError.textContent = error instanceof Error ? error.message : String(error);
});
//# sourceMappingURL=main.js.map