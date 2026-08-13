import { ControlMessageType, DeviceMessageType, ScrcpyV41Adapter, } from "@droid-web-display/scrcpy-protocol";
import { BridgeApi } from "./api.js";
import { alignedFlexSize, buildSessionRequest, validateDisplayForm, VIRTUAL_DISPLAY_PROFILES, } from "./display-config.js";
import { androidClipboardCopyMessage, androidKeyPress, clipboardMessage, clipboardShortcut, keyboardMessages, mapClientPoint, textInjectionMessages } from "./input.js";
import { WebCodecsVideoRenderer } from "./video-renderer.js";
import { WebSocketBridgeTransport } from "./websocket-transport.js";
import { WebCodecsAudioPlayer } from "./audio-player.js";
const DEVICE_DROPDOWN_REFRESH_STALE_MS = 1500;
export class DroidWebDisplayController {
    elements;
    #api = new BridgeApi();
    #adapter = new ScrcpyV41Adapter();
    #transport = null;
    #protocolSession = null;
    #serverSession = null;
    #renderer;
    #audioPlayer;
    #latestAudioStatistics = null;
    #audioTask = null;
    #clipboardSequence = 1n;
    #powerOn = true;
    #closing = false;
    #manualDisconnect = false;
    #reconnectTimer = null;
    #reconnectCount = 0;
    #lastConnectValues = null;
    #lastAndroidClipboard = "";
    #lastSentClipboard = "";
    #clipboardPollTimer = null;
    #clipboardReadAllowed = false;
    #clipboardPollBusy = false;
    #copyShortcutPending = false;
    #latestStatistics = null;
    #deviceMessageTask = null;
    #capabilities = null;
    #deviceListRefreshedAt = 0;
    #resizeObserver = null;
    #resizeTimer = null;
    #lastResizeAt = 0;
    #lastRequestedSize = null;
    #clipboardAcks = new Map();
    constructor(elements) {
        this.elements = elements;
        this.#renderer = new WebCodecsVideoRenderer(elements.canvas, (stats) => this.updateStatistics(stats));
        this.#audioPlayer = new WebCodecsAudioPlayer((stats) => this.updateAudioStatistics(stats));
        this.populateProfiles();
        this.bindEvents();
    }
    async initialize() {
        this.applyProfile(localStorage.getItem("droidwebdisplay-virtual-profile-v1") ?? "chatgpt-desktop");
        this.restoreBrowserSettings();
        await this.refreshDevices();
        await this.refreshVirtualCapabilities();
        this.updateDisplayUi();
        this.setStatus("Ready", "Select an authorized Android device and connect.");
    }
    async refreshDevices() {
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
        if (previousOption)
            previousOption.selected = true;
        else if (readyOptions.length === 1)
            readyOptions[0].selected = true;
        this.#deviceListRefreshedAt = Date.now();
        this.updateConnectAvailability();
    }
    async connect() {
        if (this.#serverSession)
            return;
        const serial = this.elements.device.value;
        if (!serial)
            throw new Error("No authorized device is selected");
        const values = this.readDisplayValues();
        this.#lastConnectValues = values;
        const errors = validateDisplayForm(values);
        if (errors.length)
            throw new Error(errors.join(" "));
        if (values.displayMode === "virtual" && !this.#capabilities?.virtualDisplaySupported) {
            throw new Error(this.#capabilities?.warnings.join(" ") || "Virtual Display mode is not supported by this device.");
        }
        this.setBusy(true);
        this.setStatus("Starting", values.displayMode === "virtual" ? "Creating Android virtual display and opening browser channels…" : "Launching scrcpy and opening browser channels…");
        try {
            const request = { ...buildSessionRequest(values, serial), audio: this.elements.audioEnabled.checked, audioCodec: "opus", audioBitRate: 128_000 };
            const serverSession = await this.#api.startSession(request);
            this.#serverSession = serverSession;
            this.#transport = new WebSocketBridgeTransport(serverSession.sessionId);
            this.#protocolSession = await this.#adapter.connect(this.#transport, {
                video: true,
                audio: this.elements.audioEnabled.checked,
                control: true,
            });
            this.setConnectedControls(true);
            this.elements.canvas.focus();
            this.#deviceMessageTask = this.consumeDeviceMessages(this.#protocolSession);
            void this.#deviceMessageTask.catch((error) => {
                if (!this.#closing && this.#serverSession)
                    console.warn("Control device-message stream ended", error);
            });
            void this.#renderer.run(this.#protocolSession).catch((error) => this.handleStreamFailure(error));
            if (this.elements.audioEnabled.checked) {
                if (this.#protocolSession.audioHeader) {
                    this.#audioPlayer.setMuted(this.elements.audioMute.textContent === "Unmute");
                    this.#audioPlayer.setVolume(Number(this.elements.audioVolume.value) / 100);
                    this.elements.audioStatus.textContent = `Audio connected · ${this.#protocolSession.audioHeader.codec}`;
                    this.#audioTask = this.#audioPlayer.run(this.#protocolSession);
                    void this.#audioTask.catch((error) => {
                        if (this.#serverSession)
                            this.elements.audioStatus.textContent = `Audio unavailable: ${errorMessage(error)}. Video and control remain active.`;
                    });
                }
                else {
                    this.elements.audioStatus.textContent = "Android audio capture is unavailable. Video and control remain active.";
                }
            }
            else {
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
                if (values.sizeMode === "flex")
                    this.startFlexResize(values);
                const display = serverSession.virtualDisplay;
                this.setStatus("Virtual display connected", `Display ${display.displayId ?? "pending"} · ${display.actualSize ?? `${values.width}x${values.height}`} · ${display.actualDpi ?? values.dpi} DPI`);
            }
            else {
                const deviceName = this.#protocolSession.device?.name ?? serverSession.serial;
                this.setStatus("Connected", `${deviceName} · H.264 · ${serverSession.options.maxFps} fps limit`);
            }
        }
        catch (error) {
            await this.cleanupSession();
            this.setStatus("Connection failed", errorMessage(error));
            this.setConnectedControls(false);
            throw error;
        }
        finally {
            this.setBusy(false);
        }
    }
    async disconnect() {
        this.#manualDisconnect = true;
        this.cancelReconnect();
        this.#closing = true;
        try {
            await this.cleanupSession();
            this.setStatus("Disconnected", "The Android session was stopped and virtual-display cleanup was requested.");
        }
        finally {
            this.#closing = false;
            this.setConnectedControls(false);
            this.#manualDisconnect = false;
        }
    }
    stopOnUnload() {
        const sessionId = this.#serverSession?.sessionId;
        if (!sessionId)
            return;
        void this.#api.stopSession(sessionId, true);
    }
    bindEvents() {
        this.elements.device.addEventListener("pointerdown", () => void this.runUiAction(() => this.refreshDevicesIfStale()));
        this.elements.device.addEventListener("focus", () => void this.runUiAction(() => this.refreshDevicesIfStale()));
        this.elements.device.addEventListener("change", () => void this.runUiAction(() => this.refreshVirtualCapabilities()));
        this.elements.connect.addEventListener("click", () => void this.runUiAction(() => this.#serverSession ? this.disconnect() : this.connect()));
        this.elements.displayMode.addEventListener("change", () => this.updateDisplayUi());
        this.elements.displayProfile.addEventListener("change", () => {
            if (this.elements.displayProfile.value !== "custom")
                this.applyProfile(this.elements.displayProfile.value);
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
        this.elements.canvas.addEventListener("contextmenu", (event) => event.preventDefault());
        this.elements.canvas.addEventListener("pointerdown", (event) => void this.pointer(event, 0));
        this.elements.canvas.addEventListener("pointermove", (event) => {
            if (event.buttons !== 0)
                void this.pointer(event, 2);
        });
        this.elements.canvas.addEventListener("pointerup", (event) => void this.pointer(event, 1));
        this.elements.canvas.addEventListener("pointercancel", (event) => void this.pointer(event, 3));
        this.elements.canvas.addEventListener("wheel", (event) => void this.scroll(event), { passive: false });
        document.addEventListener("keydown", (event) => {
            if (event.key === "F11") {
                event.preventDefault();
                void this.toggleFullscreen();
            }
        });
        this.elements.canvas.addEventListener("keydown", (event) => void this.keydown(event));
        this.elements.canvas.addEventListener("paste", (event) => {
            const text = event.clipboardData?.getData("text/plain") ?? "";
            if (!text)
                return;
            event.preventDefault();
            void this.runUiAction(() => this.pasteText(text, "Ctrl+V"));
        });
    }
    populateProfiles() {
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
    applyProfile(profileId) {
        const profile = VIRTUAL_DISPLAY_PROFILES[profileId] ?? VIRTUAL_DISPLAY_PROFILES["chatgpt-desktop"];
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
    onCustomDisplayChange() {
        if (this.elements.displayMode.value === "virtual")
            this.elements.displayProfile.value = "custom";
        this.updateDisplayUi();
    }
    displayInputs() {
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
    readDisplayValues() {
        return {
            displayMode: this.elements.displayMode.value,
            profileId: this.elements.displayProfile.value,
            sizeMode: this.elements.sizeMode.value,
            width: Number(this.elements.virtualWidth.value),
            height: Number(this.elements.virtualHeight.value),
            dpi: Number(this.elements.virtualDpi.value),
            startApp: this.elements.manualApp.value.trim(),
            forceStopBeforeLaunch: this.elements.forceStop.checked,
            keepActive: this.elements.keepActive.checked,
            systemDecorations: this.elements.systemDecorations.checked,
            destroyContentOnClose: this.elements.destroyContent.checked,
            imePolicy: this.elements.hideVirtualKeyboard.checked ? "hide" : this.elements.imePolicy.value,
            preserveAspectRatio: this.elements.preserveAspect.checked,
            videoBitRateMbps: Number(this.elements.videoBitrate.value),
            maxFps: Number(this.elements.virtualMaxFps.value),
        };
    }
    updateDisplayUi() {
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
    updateConnectAvailability() {
        if (this.#serverSession) {
            this.elements.connect.disabled = false;
            return;
        }
        const hasDevice = [...this.elements.device.options].some((option) => !option.disabled);
        const errors = validateDisplayForm(this.readDisplayValues());
        const unsupported = this.elements.displayMode.value === "virtual" && this.#capabilities?.virtualDisplaySupported === false;
        this.elements.connect.disabled = !hasDevice || this.#serverSession !== null || errors.length > 0 || unsupported;
    }
    async refreshDevicesIfStale() {
        if (Date.now() - this.#deviceListRefreshedAt < DEVICE_DROPDOWN_REFRESH_STALE_MS)
            return;
        const selected = this.elements.device.value;
        await this.refreshDevices();
        if (this.elements.device.value !== selected)
            await this.refreshVirtualCapabilities();
    }
    async refreshVirtualCapabilities() {
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
            if (localImeOption)
                localImeOption.disabled = !capabilities.localImePolicySupported;
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
            if ([...this.elements.virtualApp.options].some((option) => option.value === desired))
                this.elements.virtualApp.value = desired;
            const warningText = capabilities.warnings.length ? ` · ${capabilities.warnings.join(" ")}` : "";
            this.elements.capability.textContent = capabilities.virtualDisplaySupported
                ? `Supported · API ${capabilities.deviceApi} · codecs ${capabilities.supportedCodecs.join(", ")} · secondary-display input available${warningText}`
                : capabilities.warnings.join(" ");
            this.elements.capability.classList.toggle("error-text", !capabilities.virtualDisplaySupported);
        }
        catch (error) {
            this.#capabilities = null;
            this.elements.capability.textContent = `Capability probe failed: ${errorMessage(error)}. Physical Screen mode remains available.`;
            this.elements.capability.classList.add("error-text");
        }
        this.updateConnectAvailability();
    }
    startFlexResize(values) {
        this.stopFlexResize();
        this.#lastRequestedSize = { width: values.width, height: values.height };
        this.#resizeObserver = new ResizeObserver(() => {
            if (this.#resizeTimer !== null)
                window.clearTimeout(this.#resizeTimer);
            this.#resizeTimer = window.setTimeout(() => void this.runUiAction(() => this.applyFlexResize(values)), 250);
        });
        this.#resizeObserver.observe(this.elements.stage);
    }
    stopFlexResize() {
        this.#resizeObserver?.disconnect();
        this.#resizeObserver = null;
        if (this.#resizeTimer !== null)
            window.clearTimeout(this.#resizeTimer);
        this.#resizeTimer = null;
        this.#lastRequestedSize = null;
    }
    async applyFlexResize(values) {
        const protocol = this.#protocolSession;
        const server = this.#serverSession;
        if (!protocol || !server || server.displayMode !== "virtual" || values.sizeMode !== "flex")
            return;
        const elapsed = Date.now() - this.#lastResizeAt;
        if (elapsed < 500) {
            this.#resizeTimer = window.setTimeout(() => void this.runUiAction(() => this.applyFlexResize(values)), 500 - elapsed);
            return;
        }
        const rect = this.elements.stage.getBoundingClientRect();
        const target = alignedFlexSize(rect.width - 24, rect.height - 24, values.width, values.height, values.preserveAspectRatio);
        const previous = this.#lastRequestedSize;
        if (previous && Math.abs(target.width - previous.width) < 16 && Math.abs(target.height - previous.height) < 16)
            return;
        this.#lastRequestedSize = target;
        this.#lastResizeAt = Date.now();
        this.setStatus("Resizing virtual display", `Requesting ${target.width}×${target.height}…`);
        await protocol.sendControl({ type: ControlMessageType.ResizeDisplay, width: target.width, height: target.height });
        await this.#api.recordVirtualResize(server.sessionId, target.width, target.height);
    }
    async pointer(event, action) {
        if (!this.#protocolSession)
            return;
        event.preventDefault();
        if (action === 0) {
            this.elements.canvas.setPointerCapture(event.pointerId);
            this.elements.canvas.focus();
        }
        const size = this.#renderer.screenSize;
        if (size.width <= 0 || size.height <= 0)
            return;
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
    async scroll(event) {
        if (!this.#protocolSession)
            return;
        event.preventDefault();
        const size = this.#renderer.screenSize;
        if (size.width <= 0 || size.height <= 0)
            return;
        const position = mapClientPoint(event.clientX, event.clientY, this.elements.canvas.getBoundingClientRect(), size);
        await this.#protocolSession.sendControl({
            type: ControlMessageType.InjectScrollEvent,
            position,
            horizontal: clamp(-event.deltaX / 80, -16, 16),
            vertical: clamp(-event.deltaY / 80, -16, 16),
            buttons: event.buttons,
        });
    }
    async keydown(event) {
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
        if (!messages.length)
            return;
        event.preventDefault();
        await this.sendMessages(messages);
    }
    async rotate() {
        if (!this.#protocolSession)
            return;
        const previous = this.#renderer.screenSize;
        this.elements.rotate.disabled = true;
        this.setStatus("Rotating", "Restarting the scrcpy video capture session…");
        try {
            const resized = this.#renderer.waitForScreenSizeChange(previous);
            await this.sendMessages([{ type: ControlMessageType.RotateDevice }]);
            const size = await resized;
            this.setStatus("Connected", `Rotation completed · ${size.width}×${size.height}`);
        }
        catch (error) {
            this.setStatus("Rotation not confirmed", `${errorMessage(error)}. The session remains connected.`);
        }
        finally {
            if (this.#protocolSession)
                this.elements.rotate.disabled = false;
        }
    }
    async togglePower() {
        this.#powerOn = !this.#powerOn;
        await this.sendMessages([{ type: ControlMessageType.SetDisplayPower, on: this.#powerOn }]);
        this.elements.power.textContent = this.#powerOn ? "Screen off" : "Screen on";
    }
    async pasteClipboard(source = "PC clipboard") {
        if (!this.#protocolSession)
            return;
        let text = "";
        try {
            text = await navigator.clipboard.readText();
        }
        catch {
            text = this.elements.clipboardText.value;
            if (!text)
                throw new Error("Browser clipboard permission was denied. Paste text into the fallback box, then press Paste typed text.");
        }
        if (!text)
            text = this.elements.clipboardText.value;
        if (!text)
            throw new Error("The PC clipboard is empty. Click the Android input field first, then copy text or use the fallback box.");
        this.elements.clipboardText.value = text;
        await this.pasteText(text, source);
    }
    async pasteTypedText() {
        const text = this.elements.clipboardText.value;
        if (!text)
            throw new Error("Enter or paste text into the fallback box first");
        await this.pasteText(text, "typed text");
    }
    async pasteText(text, source) {
        const session = this.#protocolSession;
        const maximum = Math.max(1, Math.min(256, Number(this.elements.clipboardMaxKib.value) || 256)) * 1024;
        if (new TextEncoder().encode(text).byteLength > maximum)
            throw new Error(`Clipboard text exceeds the configured ${maximum / 1024} KiB limit`);
        this.#lastSentClipboard = text;
        if (!session)
            return;
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
        }
        catch (error) {
            this.resolveClipboardAcknowledgement(sequence, false);
            throw error;
        }
    }
    waitForClipboardAcknowledgement(sequence, timeoutMs = 3_000) {
        return new Promise((resolve) => {
            const waiter = {
                resolve,
                timer: window.setTimeout(() => this.resolveClipboardAcknowledgement(sequence, false), timeoutMs),
            };
            this.#clipboardAcks.set(sequence, waiter);
        });
    }
    resolveClipboardAcknowledgement(sequence, acknowledged) {
        const waiter = this.#clipboardAcks.get(sequence);
        if (!waiter)
            return;
        window.clearTimeout(waiter.timer);
        this.#clipboardAcks.delete(sequence);
        waiter.resolve(acknowledged);
    }
    async toggleFullscreen() {
        if (document.fullscreenElement)
            await document.exitFullscreen();
        else
            await this.elements.stage.requestFullscreen();
    }
    async sendMessages(messages) {
        const session = this.#protocolSession;
        if (!session)
            return;
        for (const message of messages)
            await session.sendControl(message);
    }
    async consumeDeviceMessages(session) {
        while (this.#protocolSession === session) {
            const message = await session.readDeviceMessage();
            if (message.type === DeviceMessageType.AckClipboard) {
                this.resolveClipboardAcknowledgement(message.sequence, true);
                continue;
            }
            if (message.type === DeviceMessageType.Clipboard) {
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
                    }
                    catch {
                        this.setStatus("Clipboard received", "Android clipboard is available in the clipboard panel; browser write permission was unavailable.");
                    }
                }
                else {
                    this.setStatus("Clipboard received", "Android clipboard is available in the clipboard panel.");
                }
            }
        }
    }
    async handleStreamFailure(error) {
        if (this.#closing)
            return;
        const message = errorMessage(error);
        await this.cleanupSession();
        this.setConnectedControls(false);
        this.setStatus("Stream stopped", message);
        if (!this.#manualDisconnect && this.elements.autoReconnect.checked)
            this.scheduleReconnect();
    }
    async cleanupSession() {
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
        this.#copyShortcutPending = false;
        for (const sequence of [...this.#clipboardAcks.keys()])
            this.resolveClipboardAcknowledgement(sequence, false);
        try {
            await protocol?.close();
        }
        catch {
            await transport?.close();
        }
        if (server) {
            try {
                await this.#api.stopSession(server.sessionId);
            }
            catch {
                // The WebSocket endpoint may already have stopped the session.
            }
        }
    }
    setConnectedControls(connected) {
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
        ])
            button.disabled = !connected;
        this.elements.clipboardText.disabled = !connected;
        this.elements.audioMute.disabled = !connected || !this.elements.audioEnabled.checked;
        this.elements.audioVolume.disabled = !connected || !this.elements.audioEnabled.checked;
        this.elements.audioEnabled.disabled = connected;
        this.elements.reconnect.disabled = connected || !this.elements.device.value;
        this.elements.displayMode.disabled = connected;
        this.elements.displayProfile.disabled = connected;
        for (const input of this.displayInputs())
            input.disabled = connected;
        if (!connected)
            this.updateDisplayUi();
    }
    setBusy(busy) {
        if (busy)
            this.elements.connect.disabled = true;
    }
    setStatus(title, details) {
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
    updateStatistics(stats) {
        this.#latestStatistics = stats;
        this.elements.statistics.textContent = `${stats.width}×${stats.height} · video decoded ${stats.framesDecoded} · dropped ${stats.framesDropped} · queue ${stats.decoderQueue} · sessions ${stats.sessionChanges + 1}`;
        this.updateChannelStatus();
    }
    updateAudioStatistics(stats) {
        this.#latestAudioStatistics = stats;
        this.elements.audioStatus.textContent = `${stats.codec} · ${stats.packetsDecoded} packets · ${stats.bufferedMilliseconds} ms buffered${stats.muted ? " · muted" : ""}`;
        this.updateChannelStatus();
    }
    updateChannelStatus() {
        const channels = this.#serverSession?.channels ?? [];
        const audio = this.#latestAudioStatistics ? ` · audio ${this.#latestAudioStatistics.codec}` : "";
        this.elements.sessionChannels.textContent = channels.length ? `Channels: ${channels.join(", ")}${audio}` : "No active channels.";
    }
    toggleAudioMute() {
        const muted = this.elements.audioMute.textContent !== "Unmute";
        this.#audioPlayer.setMuted(muted);
        this.elements.audioMute.textContent = muted ? "Unmute" : "Mute";
        this.saveBrowserSettings();
    }
    setAudioVolume() {
        this.#audioPlayer.setVolume(Number(this.elements.audioVolume.value) / 100);
        this.saveBrowserSettings();
    }
    async copyAndroidClipboard() {
        if (!this.#lastAndroidClipboard)
            throw new Error("No Android clipboard text has been received yet");
        await navigator.clipboard.writeText(this.#lastAndroidClipboard);
        this.setStatus("Clipboard copied", "Android clipboard was copied to the PC clipboard.");
    }
    async startClipboardPolling(requestPermission) {
        this.stopClipboardPolling();
        this.#clipboardReadAllowed = false;
        if (!this.#protocolSession || !this.elements.clipboardAutoSync.checked)
            return;
        if (!navigator.clipboard?.readText) {
            this.setStatus("Clipboard sync limited", "This browser cannot read the PC clipboard automatically. Android → PC synchronization remains available.");
            return;
        }
        let permissionState = "unsupported";
        if (navigator.permissions?.query) {
            try {
                const permission = await navigator.permissions.query({ name: "clipboard-read" });
                permissionState = permission.state;
            }
            catch {
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
        }
        catch {
            this.#clipboardReadAllowed = false;
            this.setStatus("Clipboard sync limited", "Browser clipboard permission was not granted. Use Paste manually; Android → PC synchronization remains active.");
        }
    }
    stopClipboardPolling() {
        if (this.#clipboardPollTimer !== null)
            window.clearInterval(this.#clipboardPollTimer);
        this.#clipboardPollTimer = null;
        this.#clipboardPollBusy = false;
    }
    async pollPcClipboard() {
        if (!document.hasFocus() || !this.#protocolSession || !this.elements.clipboardAutoSync.checked || !this.#clipboardReadAllowed || this.#clipboardPollBusy)
            return;
        this.#clipboardPollBusy = true;
        try {
            const text = await navigator.clipboard.readText();
            if (!text || text === this.#lastSentClipboard || text === this.#lastAndroidClipboard)
                return;
            await this.synchronizePcClipboard(text);
        }
        catch {
            // Stop polling after the first runtime permission failure instead of repeatedly opening
            // browser clipboard/paste UI and stealing focus from PC keyboard input to Android.
            this.#clipboardReadAllowed = false;
            this.stopClipboardPolling();
            this.setStatus("Clipboard sync limited", "Automatic PC clipboard access stopped after a browser permission error. Use Paste manually or toggle sync to grant access again.");
        }
        finally {
            this.#clipboardPollBusy = false;
        }
    }
    async synchronizePcClipboard(text) {
        const session = this.#protocolSession;
        if (!session)
            return;
        const maximum = Math.max(1, Math.min(256, Number(this.elements.clipboardMaxKib.value) || 256)) * 1024;
        if (new TextEncoder().encode(text).byteLength > maximum) {
            this.setStatus("Clipboard skipped", `PC clipboard exceeds the configured ${maximum / 1024} KiB limit.`);
            return;
        }
        this.#lastSentClipboard = text;
        const sequence = this.#clipboardSequence++;
        // Automatic synchronization updates Android's clipboard only.  It MUST NOT
        // request a paste action, because repeated paste=true messages steal focus
        // from the Android input method and make normal PC keyboard typing unusable.
        await session.sendControl(clipboardMessage(text, sequence, false));
        this.setStatus("Clipboard synchronized", "PC clipboard was updated on Android without pasting into the focused field.");
    }
    scheduleReconnect() {
        this.cancelReconnect();
        const maximum = Number(this.elements.reconnectAttempts.value) || 5;
        if (this.#reconnectCount >= maximum) {
            this.setStatus("Reconnect stopped", `Unable to reconnect after ${maximum} attempts.`);
            return;
        }
        const delays = [1000, 2000, 5000, 10000, 15000];
        const delay = delays[Math.min(this.#reconnectCount, delays.length - 1)];
        this.#reconnectCount += 1;
        this.setStatus("Reconnect scheduled", `Attempt ${this.#reconnectCount} of ${maximum} in ${delay / 1000} seconds.`);
        this.#reconnectTimer = window.setTimeout(() => void this.runUiAction(async () => {
            try {
                await this.refreshDevices();
                await this.connect();
            }
            catch (error) {
                if (this.elements.autoReconnect.checked)
                    this.scheduleReconnect();
                throw error;
            }
        }), delay);
    }
    cancelReconnect() {
        if (this.#reconnectTimer !== null)
            window.clearTimeout(this.#reconnectTimer);
        this.#reconnectTimer = null;
    }
    async reconnectNow() {
        this.cancelReconnect();
        if (this.#serverSession)
            await this.cleanupSession();
        await this.refreshDevices();
        await this.connect();
    }
    browserSettings() {
        return {
            schemaVersion: 1,
            display: this.readDisplayValues(),
            audio: { enabled: this.elements.audioEnabled.checked, muted: this.elements.audioMute.textContent === "Unmute", volume: Number(this.elements.audioVolume.value) },
            clipboard: { automatic: this.elements.clipboardAutoSync.checked, maximumKiB: Number(this.elements.clipboardMaxKib.value) },
            reconnect: { enabled: this.elements.autoReconnect.checked, attempts: Number(this.elements.reconnectAttempts.value) },
        };
    }
    saveBrowserSettings() {
        localStorage.setItem("droidwebdisplay-settings-v1", JSON.stringify(this.browserSettings()));
    }
    restoreBrowserSettings() {
        try {
            const raw = localStorage.getItem("droidwebdisplay-settings-v1");
            if (!raw)
                return;
            this.applyImportedSettings(JSON.parse(raw));
        }
        catch {
            localStorage.removeItem("droidwebdisplay-settings-v1");
        }
    }
    applyImportedSettings(value) {
        const display = value.display;
        const audio = value.audio;
        const clipboard = value.clipboard;
        const reconnect = value.reconnect;
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
    exportSettings() {
        this.downloadJson("droidwebdisplay-settings.json", this.browserSettings());
        this.elements.settingsStatus.textContent = "Settings exported.";
    }
    async importSettings() {
        const file = this.elements.settingsFile.files?.[0];
        if (!file)
            return;
        const parsed = JSON.parse(await file.text());
        if (parsed.schemaVersion !== 1)
            throw new Error("Unsupported settings file version");
        this.applyImportedSettings(parsed);
        this.saveBrowserSettings();
        this.elements.settingsStatus.textContent = "Settings imported. Reconnect to apply session options.";
        this.elements.settingsFile.value = "";
    }
    downloadJson(filename, value) {
        const blob = new Blob([`${JSON.stringify(value, null, 2)}\n`], { type: "application/json" });
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
        URL.revokeObjectURL(link.href);
    }
    async runUiAction(action) {
        try {
            await action();
        }
        catch (error) {
            this.setStatus("Error", errorMessage(error));
        }
    }
}
function deviceLabel(device) {
    const name = device.model ?? device.serial;
    const version = device.android_version ? `Android ${device.android_version}` : device.state;
    return `${name} · ${version}${device.ready ? "" : ` · ${device.state}`}`;
}
function errorMessage(error) {
    return error instanceof Error ? error.message : String(error);
}
function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
}
//# sourceMappingURL=controller.js.map