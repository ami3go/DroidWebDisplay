import { inspectBrowserCapabilities } from "./browser-support.js";
import { DroidWebDisplayController } from "./controller.js";
import { CLIPBOARD_STATUS } from "./clipboard-status.js";
import { clipboardShortcut, isEditableTarget } from "./input.js";
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
function bindAndroidCopyWriteThrough() {
    const button = required("#clipboard-copy-android");
    const canvas = required("#screen");
    const clipboardText = required("#clipboard-text");
    const status = required("#status");
    const details = required("#details");
    const statusContainer = required("#connection-status");
    let generation = 0;
    /** Mirror the side effects of controller.setStatus for the fields that describe
        the status line itself. data-state is deliberately untouched: a copy does
        not change the connection state, but title and aria-label describe the
        visible text and go stale if only textContent is written. */
    const writeStatus = (headline, detail) => {
        status.textContent = headline;
        details.textContent = detail;
        statusContainer.title = detail;
        statusContainer.setAttribute("aria-label", `${statusContainer.dataset.state ?? "unknown"}: ${headline}. ${detail}`);
    };
    const finishCopy = async () => {
        // Ctrl+C reaches this listener anywhere outside editable/selected PC text,
        // including with no device attached. The controller suppresses its own
        // "not confirmed" message in that case, so claiming a failed copy here
        // would reinstate the very message it takes care to avoid.
        if (statusContainer.dataset.state !== "connected")
            return;
        const request = ++generation;
        const initialText = clipboardText.value;
        const initialStatus = status.textContent?.trim() ?? "";
        const deadline = performance.now() + 1200;
        let responseObserved = false;
        while (performance.now() < deadline) {
            if (request !== generation)
                return;
            const currentStatus = status.textContent?.trim() ?? "";
            const textChanged = clipboardText.value !== initialText;
            const statusChanged = currentStatus !== initialStatus;
            if (statusChanged && currentStatus === CLIPBOARD_STATUS.notConfirmed)
                return;
            if ((textChanged || statusChanged) && currentStatus === CLIPBOARD_STATUS.copied)
                return;
            if (textChanged || (statusChanged && currentStatus === CLIPBOARD_STATUS.received)) {
                responseObserved = true;
                break;
            }
            await new Promise((resolve) => window.setTimeout(resolve, 20));
        }
        if (request !== generation)
            return;
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
            if (request !== generation)
                return;
            writeStatus(CLIPBOARD_STATUS.copied, "Android selection was copied to the PC clipboard.");
            return;
        }
        catch {
            // Every other exit re-checks the generation; without it here a superseded
            // copy still yanks focus and writes its result over the newer request.
            if (request !== generation)
                return;
            // execCommand copies the live selection, so it can only be trusted while
            // the textarea still holds the text this request validated.
            if (clipboardText.value !== text)
                return;
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
            if (previouslyFocused instanceof HTMLElement)
                previouslyFocused.focus();
            else
                canvas.focus();
            if (request !== generation)
                return;
            if (copied) {
                writeStatus(CLIPBOARD_STATUS.copied, "Android selection was copied to the PC clipboard using the browser fallback.");
            }
            else {
                writeStatus(CLIPBOARD_STATUS.received, "Android clipboard reached the browser, but the browser blocked writing to the PC clipboard.");
            }
        }
    };
    button.addEventListener("click", () => void finishCopy());
    document.addEventListener("keydown", (event) => {
        // Reuse the controller's predicate instead of restating it: a copy of this
        // condition drifts out of step with the keydown handler it shadows.
        const selection = document.getSelection();
        if (event.repeat
            || isEditableTarget(event.target)
            || (selection !== null && !selection.isCollapsed)
            || clipboardShortcut(event) !== "copy")
            return;
        void finishCopy();
    });
}
function browserGpuRenderer() {
    try {
        const canvas = document.createElement("canvas");
        const gl = canvas.getContext("webgl");
        if (!gl)
            return "WebGL unavailable";
        const debug = gl.getExtension("WEBGL_debug_renderer_info");
        const value = gl.getParameter(debug?.UNMASKED_RENDERER_WEBGL ?? gl.RENDERER);
        return typeof value === "string" && value.trim() ? value.trim() : "WebGL available";
    }
    catch {
        return "GPU renderer unavailable";
    }
}
function installBrowserDiagnostics(capabilities) {
    const statistics = required("#statistics");
    const gpu = browserGpuRenderer();
    const webCodecs = capabilities.supported ? "WebCodecs ready" : `missing ${capabilities.missing.join(", ")}`;
    const cpu = capabilities.hardwareConcurrency === null ? "CPU ?" : `${capabilities.hardwareConcurrency} logical CPU`;
    const summary = `${capabilities.browserName} · ${capabilities.platform} · ${webCodecs} · ${cpu} · GPU ${gpu}`;
    statistics.textContent = summary;
    statistics.dataset.browserDiagnostics = summary;
    statistics.title = `${summary}. If controls work but video is black: update Chrome/Edge and the GPU driver; if needed disable browser hardware acceleration, restart the browser, then reconnect.`;
}
function bindAdbDeviceGuidance() {
    const device = required("#device");
    const status = required("#status");
    const details = required("#details");
    const statusContainer = required("#connection-status");
    const guidanceTitles = new Set([
        "USB authorization required",
        "ADB device offline",
        "ADB access blocked",
        "No Android device",
        "ADB device not ready",
    ]);
    const update = () => {
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
        }
        else if (labels.includes("no permissions")) {
            status.textContent = "ADB access blocked";
            details.textContent = "The phone is visible but ADB cannot access it. On Windows, install/update the phone OEM USB driver and reconnect USB.";
        }
        else if (labels.includes("offline")) {
            status.textContent = "ADB device offline";
            details.textContent = "Reconnect USB, unlock the phone, and toggle USB debugging if the device remains offline.";
        }
        else if (!options.length) {
            status.textContent = "No Android device";
            details.textContent = "Connect the phone with USB debugging enabled. Windows may require the manufacturer/OEM USB driver.";
        }
        else {
            status.textContent = "ADB device not ready";
            details.textContent = `Connected device state: ${options[0]?.textContent?.trim() || "unknown"}. Resolve the USB/Android state and refresh devices.`;
        }
        statusContainer.setAttribute("aria-label", `disconnected: ${status.textContent}. ${details.textContent}`);
    };
    new MutationObserver(update).observe(device, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
    device.addEventListener("change", update);
    update();
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
        installBrowserDiagnostics(capabilities);
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
            quickAppConfigure: required("#quick-app-configure"),
            quickAppHeader: required("#quick-app-header"),
            quickAppAdd: required("#quick-app-add"),
            quickAppList: required("#quick-app-list"),
            quickAppSettingsStatus: required("#quick-app-settings-status"),
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
        bindAndroidCopyWriteThrough();
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
            contextUploadFile: required("#context-upload-file"),
            customDestinationRow: required("#custom-destination-row"),
            customDestinationPath: required("#custom-destination-path"),
            duplicatePolicy: required("#duplicate-policy"),
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
            stage: required("#stage"),
            stageDropOverlay: required("#stage-drop-overlay"),
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
        window.addEventListener("beforeunload", () => { controller.stopOnUnload(); runningAppController.close(); transferController.close(); autoDownloadController.close(); });
        void controller.initialize()
            .then(() => {
            bindAdbDeviceGuidance();
            return Promise.all([transferController.initialize(), autoDownloadController.initialize(), runningAppController.initialize()]);
        })
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