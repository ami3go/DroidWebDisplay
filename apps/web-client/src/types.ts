export interface AndroidDevice {
  readonly serial: string;
  readonly state: string;
  readonly model: string | null;
  readonly manufacturer: string | null;
  readonly android_version: string | null;
  readonly sdk: number | null;
  readonly ready: boolean;
  readonly authorizationRequired: boolean;
}

export type DisplayMode = "physical" | "virtual";
export type VirtualDisplaySizeMode = "fixed" | "flex";
export type DisplayImePolicy = "default" | "local" | "fallback" | "hide";

export interface VirtualDisplayConfigDto {
  readonly profileId: string;
  readonly sizeMode: VirtualDisplaySizeMode;
  readonly width: number;
  readonly height: number;
  readonly dpi: number;
  readonly startApp: string;
  readonly forceStopBeforeLaunch: boolean;
  readonly keepActive: boolean;
  readonly systemDecorations: boolean;
  readonly destroyContentOnClose: boolean;
  readonly imePolicy: DisplayImePolicy;
  readonly preserveAspectRatio: boolean;
}

export interface SessionOptionsDto {
  readonly video: boolean;
  readonly audio: boolean;
  readonly control: boolean;
  readonly audioCodec: string;
  readonly audioBitRate: number;
  readonly videoCodec: string;
  readonly maxSize: number;
  readonly videoBitRate: number;
  readonly maxFps: number;
  readonly displayMode: DisplayMode;
  readonly virtualDisplay: VirtualDisplayConfigDto | null;
}

export interface VirtualDisplayDiagnosticDto {
  readonly requested: boolean;
  readonly supported: boolean | null;
  readonly displayId: number | null;
  readonly requestedSize: string | null;
  readonly actualSize: string | null;
  readonly requestedDpi: number | null;
  readonly actualDpi: number | null;
  readonly flexDisplay: boolean;
  readonly systemDecorations: boolean | null;
  readonly destroyContentOnClose: boolean | null;
  readonly imePolicy: string | null;
  readonly startApp: string | null;
  readonly startAppPayload: string | null;
  readonly applicationLaunchResult: string;
  readonly application: string | null;
  readonly resizeCount: number;
  readonly cleanupResult: string;
}

export interface ChannelDiagnosticDto {
  readonly name: string;
  readonly bytesFromDevice: number;
  readonly bytesToDevice: number;
  readonly attached: boolean;
  readonly relayCloseReason: string | null;
}

export interface SessionDto {
  readonly sessionId: string;
  readonly serial: string;
  readonly state: string;
  readonly channels: readonly string[];
  readonly options: SessionOptionsDto;
  readonly displayMode: DisplayMode;
  readonly virtualDisplay: VirtualDisplayDiagnosticDto;
  readonly error: string | null;
  readonly stopReason: string | null;
  readonly dummyByteValidated: boolean;
  readonly firstChannelAttempts: number;
  readonly channelDiagnostics?: Readonly<Record<string, ChannelDiagnosticDto>>;
}

export interface DeviceListResponse {
  readonly devices: readonly AndroidDevice[];
}

export interface SessionListResponse {
  readonly sessions: readonly SessionDto[];
}

export interface BrowserSupportResponse {
  readonly engine: string;
  readonly required: readonly string[];
  readonly videoCodec: string;
  readonly audioCodec: string;
  readonly optionalAudio: readonly string[];
  readonly softwareDecoderFallback: boolean;
}

export interface VirtualDisplayCapabilities {
  readonly virtualDisplaySupported: boolean;
  readonly flexDisplaySupported: boolean;
  readonly secondaryDisplayControlSupported: boolean;
  readonly localImePolicySupported: boolean;
  readonly installedAppsQuerySupported: boolean;
  readonly requestedAppInstalled: boolean | null;
  readonly requestedPackage: string | null;
  readonly minimumApi: number;
  readonly deviceApi: number | null;
  readonly supportedCodecs: readonly string[];
  readonly browserSupportedCodecs: readonly string[];
  readonly warnings: readonly string[];
}

export interface LaunchableAppDto {
  readonly label: string;
  readonly packageName: string;
  readonly secondaryDisplayCompatibility: "unknown" | "supported" | "unsupported";
}

export interface LaunchableAppsResponse {
  readonly apps: readonly LaunchableAppDto[];
}

export interface VirtualDisplayProfilesResponse {
  readonly profiles: readonly (VirtualDisplayConfigDto & {
    readonly videoCodec: string;
    readonly videoBitRate: number;
    readonly maxFps: number;
  })[];
}

export interface AndroidStorageEntryDto {
  readonly name: string;
  readonly path: string;
  readonly mode: number;
  readonly size: number;
  readonly modifiedAt: number;
  readonly isDirectory: boolean;
}

export interface AndroidStorageResponse {
  readonly path: string;
  readonly entries: readonly AndroidStorageEntryDto[];
}

export type TransferState = "queued" | "preparing" | "transferring" | "verifying" | "completed" | "cancelled" | "failed" | "interrupted";
export type TransferDirection = "upload" | "download";
export type DuplicatePolicy = "rename" | "overwrite" | "fail";

export interface TransferDto {
  readonly transferId: string;
  readonly direction: TransferDirection;
  readonly serial: string;
  readonly sourcePath: string;
  readonly destinationPath: string;
  readonly filename: string;
  readonly state: TransferState;
  readonly size: number | null;
  readonly bytesTransferred: number;
  readonly speedBytesPerSecond: number;
  readonly progress: number | null;
  readonly createdAt: number;
  readonly startedAt: number | null;
  readonly endedAt: number | null;
  readonly retryCount: number;
  readonly error: string | null;
  readonly verification: string | null;
  readonly duplicatePolicy: DuplicatePolicy;
  readonly destinationProfile: string | null;
}

export interface TransferListResponse {
  readonly transfers: readonly TransferDto[];
}

export interface DestinationProfileDto {
  readonly id: string;
  readonly path: string;
}

export interface DestinationProfileResponse {
  readonly profiles: readonly DestinationProfileDto[];
}

export interface AndroidStorageRootDto {
  readonly id: string;
  readonly label: string;
  readonly path: string;
}

export interface AndroidStorageRootsResponse {
  readonly roots: readonly AndroidStorageRootDto[];
  readonly defaultPath: string;
}

export interface AutoDownloadConfigDto {
  readonly enabled: boolean;
  readonly pcToAndroidEnabled: boolean;
  readonly serial: string | null;
  readonly sourcePath: string;
  readonly destinationProfile: string;
  readonly duplicatePolicy: DuplicatePolicy;
  readonly uploadDuplicatePolicy: DuplicatePolicy;
  readonly scanIntervalSeconds: number;
  readonly stabilitySeconds: number;
  readonly stabilityObservations: number;
  readonly includeExisting: boolean;
  readonly includeExistingPc: boolean;
  readonly deleteAfterVerified: boolean;
}

export interface AutoDownloadFileDto {
  readonly path: string;
  readonly size: number;
  readonly modifiedAt: number;
  readonly fingerprint: string;
  readonly firstSeenAt: number;
  readonly lastChangedAt: number;
  readonly stableObservations: number;
  readonly status: string;
  readonly transferId: string | null;
  readonly retryCount: number;
  readonly nextRetryAt: number;
  readonly localDestination: string | null;
  readonly deletionResult: string | null;
  readonly error: string | null;
}


export interface AutoUploadFileDto {
  readonly path: string;
  readonly size: number;
  readonly modifiedNs: number;
  readonly fingerprint: string;
  readonly firstSeenAt: number;
  readonly lastChangedAt: number;
  readonly stableObservations: number;
  readonly status: string;
  readonly transferId: string | null;
  readonly retryCount: number;
  readonly nextRetryAt: number;
  readonly remoteDestination: string | null;
  readonly error: string | null;
}

export interface AutoDownloadNotificationDto {
  readonly timestamp: number;
  readonly event: string;
  readonly message: string;
  readonly path?: string;
  readonly destination?: string;
  readonly transferId?: string;
  readonly error?: string;
}

export interface AutoDownloadSnapshotDto {
  readonly schemaVersion: number;
  readonly config: AutoDownloadConfigDto;
  readonly runtime: {
    readonly state: string;
    readonly baselineInitialized: boolean;
    readonly pcBaselineInitialized: boolean;
    readonly lastScanAt: number | null;
    readonly lastSuccessAt: number | null;
    readonly lastError: string | null;
    readonly scanCount: number;
    readonly filesSeen: number;
    readonly pcFilesSeen: number;
    readonly downloadsQueued: number;
    readonly downloadsCompleted: number;
    readonly uploadsQueued: number;
    readonly uploadsCompleted: number;
    readonly deletionsCompleted: number;
    readonly notifications: readonly AutoDownloadNotificationDto[];
  };
  readonly files: readonly AutoDownloadFileDto[];
  readonly localFiles: readonly AutoUploadFileDto[];
  readonly processedFingerprints: number;
  readonly processedPcFingerprints: number;
}

export interface RunningGuiAppDto {
  readonly taskId: number;
  readonly packageName: string;
  readonly componentName: string;
  readonly displayId: number | null;
  readonly visible: boolean;
  readonly resumed: boolean;
  readonly label: string;
  readonly hasGui: true;
}

export interface RunningAppsResponse {
  readonly serial: string;
  readonly apps: readonly RunningGuiAppDto[];
  readonly moveStrategy: "start-activity-on-display";
}

export interface MoveRunningAppResponse {
  readonly status: "already-on-target" | "moved" | "launch-sent-unverified";
  readonly moved: boolean;
  readonly verified: boolean;
  readonly sessionId: string;
  readonly displayId: number;
  readonly app: RunningGuiAppDto;
  readonly strategy: "none" | "start-activity-on-display";
  readonly output?: string;
}
