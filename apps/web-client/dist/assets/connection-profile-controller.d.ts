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
    audio: {
        enabled: boolean;
        muted: boolean;
        volume: number;
    };
    clipboard: {
        automatic: boolean;
        maximumKiB: number;
    };
    reconnect: {
        enabled: boolean;
        attempts: 3 | 5 | 10;
    };
    video: {
        encoderMode: "auto" | "selected";
        encoder: string | null;
    };
}
interface StoredConnectionProfile extends ConnectionProfileInput {
    schemaVersion: 1;
    id: string;
    createdAt: string;
    updatedAt: string;
    lastUsedAt: string | null;
}
interface PortableProfileDocument {
    kind: "droidwebdisplay-connection-profile";
    exportVersion: 1;
    profileSchemaVersion: 1;
    profile: ConnectionProfileInput;
}
export declare function parsePortableConnectionProfile(value: unknown): ConnectionProfileInput;
export declare function portableConnectionProfile(profile: StoredConnectionProfile): PortableProfileDocument;
export declare class ConnectionProfileController {
    #private;
    initialize(): Promise<void>;
    private installUi;
    private renameDisplayPresetUi;
    private bindUi;
    private bindDirtyTracking;
    private markDirty;
    private refreshProfiles;
    private selectProfile;
    private selectedProfile;
    private renderSelectionState;
    private currentDevice;
    private reconnectAttempts;
    private captureCurrent;
    private loadAndConnectSelected;
    private loadAndConnectProfile;
    private finishProfileConnection;
    private applyProfileSettings;
    private selectExactDevice;
    private applyEncoderPreference;
    private validateVirtualCapability;
    private beginWaiting;
    private pollWaitingProfile;
    private cancelWaiting;
    private suggestedName;
    private saveCurrent;
    private updateCurrent;
    private renameSelected;
    private deleteSelected;
    private exportSelected;
    private importSelectedFile;
    private downloadJson;
    private changeDefault;
    private setMainStatus;
    private setStatus;
    private run;
}
export {};
