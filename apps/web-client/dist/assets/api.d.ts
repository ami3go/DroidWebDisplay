import type { AndroidStorageResponse, AndroidStorageRootsResponse, AutoDownloadConfigDto, AutoDownloadSnapshotDto, BrowserSupportResponse, DestinationProfileResponse, DeviceListResponse, DuplicatePolicy, LaunchableAppsResponse, MoveRunningAppResponse, RunningAppsResponse, SessionDto, SessionListResponse, TransferDto, TransferListResponse, VirtualDisplayCapabilities, VirtualDisplayProfilesResponse } from "./types.js";
export interface AuthSessionDto {
    readonly sessionId: string;
    readonly createdAt: number;
    readonly lastSeenAt: number;
    readonly expiresAt: number | null;
    readonly duration: string;
    readonly customSeconds: number | null;
    readonly label: string;
    readonly userAgent: string;
    readonly revokedAt: number | null;
    readonly revocationReason: string | null;
    readonly current?: boolean;
}
export interface AuthStatusDto {
    readonly configured: boolean;
    readonly authenticated: boolean;
    readonly trustModel: "pc-local";
    readonly phoneAuthoritative: false;
    readonly csrfToken: string | null;
    readonly currentSession: AuthSessionDto | null;
    readonly durationChoices: readonly string[];
    readonly customDuration: {
        readonly minimumSeconds: number;
        readonly maximumSeconds: number;
    };
}
export declare function setSharedCsrfToken(value: string | null): void;
export declare class BridgeApiError extends Error {
    readonly status: number;
    readonly details: unknown;
    constructor(message: string, status: number, details: unknown);
}
export interface StartSessionRequest {
    readonly serial?: string;
    readonly video?: boolean;
    readonly audio?: boolean;
    readonly control?: boolean;
    readonly audioCodec?: "opus" | "aac" | "flac" | "raw";
    readonly audioBitRate?: number;
    readonly videoCodec?: "h264" | "h265" | "av1";
    readonly maxSize?: number;
    readonly videoBitRate?: number;
    readonly maxFps?: number;
    readonly displayMode?: "physical" | "virtual";
    readonly virtualDisplay?: Record<string, unknown>;
}
export declare class BridgeApi {
    private readonly baseUrl;
    private readonly fetchImpl;
    constructor(baseUrl?: string, fetchImpl?: typeof fetch);
    authStatus(): Promise<AuthStatusDto>;
    authSetup(request: {
        pin: string;
        confirmPin: string;
        duration: string;
        customSeconds?: number;
        label?: string;
    }): Promise<AuthStatusDto>;
    authLogin(request: {
        pin: string;
        duration: string;
        customSeconds?: number;
        label?: string;
    }): Promise<AuthStatusDto>;
    authLogout(): Promise<{
        authenticated: false;
        status: string;
    }>;
    authSessions(): Promise<{
        sessions: AuthSessionDto[];
        trustModel: "pc-local";
    }>;
    revokeAuthSession(sessionId: string): Promise<{
        revoked: boolean;
        currentSessionRevoked: boolean;
    }>;
    revokeAllAuthSessions(pin: string): Promise<{
        revoked: number;
        authenticated: false;
    }>;
    changeAuthPin(currentPin: string, newPin: string, confirmPin: string): Promise<{
        changed: boolean;
        authenticated: false;
    }>;
    authAudit(): Promise<{
        events: Array<Record<string, unknown>>;
        sensitiveValuesLogged: false;
    }>;
    devices(): Promise<DeviceListResponse>;
    browserSupport(): Promise<BrowserSupportResponse>;
    virtualDisplayCapabilities(serial: string, startApp?: string): Promise<VirtualDisplayCapabilities>;
    launchableApps(serial: string): Promise<LaunchableAppsResponse>;
    runningApps(serial: string): Promise<RunningAppsResponse>;
    moveRunningApp(request: {
        sessionId: string;
        taskId: number;
        componentName: string;
    }): Promise<MoveRunningAppResponse>;
    virtualDisplayProfiles(): Promise<VirtualDisplayProfilesResponse>;
    sessions(): Promise<SessionListResponse>;
    startSession(request: StartSessionRequest): Promise<SessionDto>;
    androidStorage(serial: string, path: string): Promise<AndroidStorageResponse>;
    deleteAndroidStorage(serial: string, path: string): Promise<{
        deleted: boolean;
        path: string;
        isDirectory: boolean;
    }>;
    androidStorageRoots(serial?: string): Promise<AndroidStorageRootsResponse>;
    autoDownload(): Promise<AutoDownloadSnapshotDto>;
    configureAutoDownload(config: AutoDownloadConfigDto): Promise<AutoDownloadSnapshotDto>;
    scanAutoDownload(): Promise<AutoDownloadSnapshotDto>;
    resetAutoDownload(): Promise<AutoDownloadSnapshotDto>;
    destinationProfiles(): Promise<DestinationProfileResponse>;
    transfers(): Promise<TransferListResponse>;
    openDestinationProfile(profileId: string): Promise<{
        profileId: string;
        path: string;
        opened: boolean;
    }>;
    openDestinationPath(path: string): Promise<{
        path: string;
        opened: boolean;
    }>;
    uploadFile(request: {
        serial: string;
        file: File;
        destinationPath?: string | undefined;
        duplicatePolicy: DuplicatePolicy;
    }): Promise<TransferDto>;
    downloadFile(request: {
        serial: string;
        sourcePath: string;
        destinationProfile: string;
        destinationPath?: string;
        duplicatePolicy: DuplicatePolicy;
    }): Promise<TransferDto>;
    cancelTransfer(transferId: string): Promise<TransferDto>;
    retryTransfer(transferId: string): Promise<TransferDto>;
    recordVirtualResize(sessionId: string, width: number, height: number): Promise<SessionDto>;
    recordApplicationLaunch(sessionId: string, result: "sent" | "success" | "failed"): Promise<SessionDto>;
    getSession(sessionId: string): Promise<SessionDto>;
    stopSession(sessionId: string, keepalive?: boolean): Promise<SessionDto | null>;
    networkStatus(): Promise<{
        active: NetworkConfigDto;
        url: string;
        restartSupported: boolean;
        lanEnabled: boolean;
    }>;
    networkInterfaces(): Promise<{
        interfaces: NetworkInterfaceDto[];
    }>;
    networkConfig(): Promise<{
        config: NetworkConfigDto;
        activeMode: string;
    }>;
    validateNetworkConfig(config: NetworkConfigRequestDto): Promise<Record<string, unknown>>;
    applyNetworkConfig(config: NetworkConfigRequestDto): Promise<{
        applied: boolean;
        restartRequired: boolean;
        restartScheduled: boolean;
        url: string;
        revokedSessions: number;
    }>;
    disableNetworkAccess(currentPin: string): Promise<{
        disabled: boolean;
        restartRequired: boolean;
        restartScheduled: boolean;
        url: string;
    }>;
    private request;
}
export interface NetworkInterfaceDto {
    readonly name: string;
    readonly address: string;
    readonly prefixLength: number;
    readonly network: string;
    readonly private: boolean;
    readonly loopback: boolean;
    readonly adapterType: string;
}
export interface NetworkConfigDto {
    readonly schemaVersion?: number;
    readonly mode: "local-only" | "lan-https";
    readonly bindAddress: string;
    readonly port: number;
    readonly allowedNetworks: readonly string[];
    readonly hostname?: string | null;
    readonly tls?: {
        readonly enabled: boolean;
        readonly certificatePath: string | null;
        readonly privateKeyPath: string | null;
        readonly certificateSource: string;
    };
    readonly firewall?: {
        readonly manageRule: boolean;
        readonly ruleName: string;
    };
}
export interface NetworkConfigRequestDto {
    readonly mode: "local-only" | "lan-https";
    readonly bindAddress: string;
    readonly port: number;
    readonly allowedNetworks: readonly string[];
    readonly hostname?: string | undefined;
    readonly certificateSource: "generated" | "existing";
    readonly certificatePath?: string | undefined;
    readonly privateKeyPath?: string | undefined;
    readonly certificateValidityDays: number;
    readonly manageFirewall: boolean;
    readonly currentPin: string;
}
