import type {
  AndroidStorageResponse,
  AndroidStorageRootsResponse,
  AutoDownloadConfigDto,
  AutoDownloadSnapshotDto,
  BrowserSupportResponse,
  DestinationProfileResponse,
  DeviceListResponse,
  DuplicatePolicy,
  LaunchableAppsResponse,
  MoveRunningAppResponse,
  RunningAppsResponse,
  SessionDto,
  SessionListResponse,
  TransferDto,
  TransferListResponse,
  VirtualDisplayCapabilities,
  VirtualDisplayProfilesResponse,
} from "./types.js";

const windowFetch: typeof fetch = (input, init) => globalThis.fetch(input, init);

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
  readonly customDuration: { readonly minimumSeconds: number; readonly maximumSeconds: number };
}

let sharedCsrfToken: string | null = null;

export function setSharedCsrfToken(value: string | null): void {
  sharedCsrfToken = value;
}

export class BridgeApiError extends Error {
  public constructor(
    message: string,
    public readonly status: number,
    public readonly details: unknown,
  ) {
    super(message);
    this.name = "BridgeApiError";
  }
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

export class BridgeApi {
  public constructor(
    private readonly baseUrl = "",
    private readonly fetchImpl: typeof fetch = windowFetch,
  ) {}

  public async authStatus(): Promise<AuthStatusDto> {
    const value = await this.request<AuthStatusDto>("/api/v1/auth/status", undefined, true);
    setSharedCsrfToken(value.csrfToken);
    return value;
  }

  public async authSetup(request: { pin: string; confirmPin: string; duration: string; customSeconds?: number; label?: string }): Promise<AuthStatusDto> {
    const value = await this.request<AuthStatusDto>("/api/v1/auth/setup", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    }, true);
    setSharedCsrfToken(value.csrfToken);
    return value;
  }

  public async authLogin(request: { pin: string; duration: string; customSeconds?: number; label?: string }): Promise<AuthStatusDto> {
    const value = await this.request<AuthStatusDto>("/api/v1/auth/login", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    }, true);
    setSharedCsrfToken(value.csrfToken);
    return value;
  }

  public async authLogout(): Promise<{ authenticated: false; status: string }> {
    const value = await this.request<{ authenticated: false; status: string }>("/api/v1/auth/logout", { method: "POST" });
    setSharedCsrfToken(null);
    return value;
  }

  public async authSessions(): Promise<{ sessions: AuthSessionDto[]; trustModel: "pc-local" }> {
    return this.request("/api/v1/auth/sessions");
  }

  public async revokeAuthSession(sessionId: string): Promise<{ revoked: boolean; currentSessionRevoked: boolean }> {
    return this.request(`/api/v1/auth/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  }

  public async revokeAllAuthSessions(pin: string): Promise<{ revoked: number; authenticated: false }> {
    const value = await this.request<{ revoked: number; authenticated: false }>("/api/v1/auth/sessions/revoke-all", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ pin }),
    });
    setSharedCsrfToken(null);
    return value;
  }

  public async changeAuthPin(currentPin: string, newPin: string, confirmPin: string): Promise<{ changed: boolean; authenticated: false }> {
    const value = await this.request<{ changed: boolean; authenticated: false }>("/api/v1/auth/change-pin", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ currentPin, newPin, confirmPin }),
    });
    setSharedCsrfToken(null);
    return value;
  }

  public async authAudit(): Promise<{ events: Array<Record<string, unknown>>; sensitiveValuesLogged: false }> {
    return this.request("/api/v1/auth/audit");
  }

  public async devices(): Promise<DeviceListResponse> {
    return this.request<DeviceListResponse>("/api/v1/devices");
  }

  public async browserSupport(): Promise<BrowserSupportResponse> {
    return this.request<BrowserSupportResponse>("/api/v1/browser-support");
  }

  public async virtualDisplayCapabilities(serial: string, startApp = "com.openai.chatgpt"): Promise<VirtualDisplayCapabilities> {
    const query = new URLSearchParams({ startApp });
    return this.request<VirtualDisplayCapabilities>(`/api/v1/devices/${encodeURIComponent(serial)}/virtual-display-capabilities?${query.toString()}`);
  }

  public async launchableApps(serial: string): Promise<LaunchableAppsResponse> {
    return this.request<LaunchableAppsResponse>(`/api/v1/devices/${encodeURIComponent(serial)}/apps`);
  }

  public async runningApps(serial: string): Promise<RunningAppsResponse> {
    return this.request<RunningAppsResponse>(`/api/v1/devices/${encodeURIComponent(serial)}/running-apps`);
  }

  public async moveRunningApp(request: { sessionId: string; taskId: number; componentName: string }): Promise<MoveRunningAppResponse> {
    return this.request<MoveRunningAppResponse>(`/api/v1/sessions/${encodeURIComponent(request.sessionId)}/virtual-display/move-running-app`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ taskId: request.taskId, componentName: request.componentName }),
    });
  }

  public async virtualDisplayProfiles(): Promise<VirtualDisplayProfilesResponse> {
    return this.request<VirtualDisplayProfilesResponse>("/api/v1/virtual-display-profiles");
  }

  public async sessions(): Promise<SessionListResponse> {
    return this.request<SessionListResponse>("/api/v1/sessions");
  }

  public async startSession(request: StartSessionRequest): Promise<SessionDto> {
    return this.request<SessionDto>("/api/v1/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        video: true,
        audio: false,
        control: true,
        audioCodec: "opus",
        audioBitRate: 128_000,
        videoCodec: "h264",
        maxSize: 1920,
        videoBitRate: 8_000_000,
        maxFps: 30,
        displayMode: "physical",
        ...request,
      }),
    });
  }

  public async androidStorage(serial: string, path: string): Promise<AndroidStorageResponse> {
    const query = new URLSearchParams({ serial, path });
    return this.request<AndroidStorageResponse>(`/api/v1/storage/android?${query.toString()}`);
  }

  public async androidStorageRoots(serial?: string): Promise<AndroidStorageRootsResponse> {
    const query = serial ? `?${new URLSearchParams({ serial }).toString()}` : "";
    return this.request<AndroidStorageRootsResponse>(`/api/v1/storage/android-roots${query}`);
  }

  public async autoDownload(): Promise<AutoDownloadSnapshotDto> {
    return this.request<AutoDownloadSnapshotDto>("/api/v1/auto-download");
  }

  public async configureAutoDownload(config: AutoDownloadConfigDto): Promise<AutoDownloadSnapshotDto> {
    return this.request<AutoDownloadSnapshotDto>("/api/v1/auto-download", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(config),
    });
  }

  public async scanAutoDownload(): Promise<AutoDownloadSnapshotDto> {
    return this.request<AutoDownloadSnapshotDto>("/api/v1/auto-download/scan", { method: "POST" });
  }

  public async resetAutoDownload(): Promise<AutoDownloadSnapshotDto> {
    return this.request<AutoDownloadSnapshotDto>("/api/v1/auto-download/reset", { method: "POST" });
  }

  public async destinationProfiles(): Promise<DestinationProfileResponse> {
    return this.request<DestinationProfileResponse>("/api/v1/destination-profiles");
  }

  public async transfers(): Promise<TransferListResponse> {
    return this.request<TransferListResponse>("/api/v1/transfers");
  }

  public async openDestinationProfile(profileId: string): Promise<{ profileId: string; path: string; opened: boolean }> {
    return this.request(`/api/v1/destination-profiles/${encodeURIComponent(profileId)}/open`, { method: "POST" });
  }

  public async uploadFile(request: { serial: string; file: File; destinationPath: string; duplicatePolicy: DuplicatePolicy }): Promise<TransferDto> {
    const form = new FormData();
    form.set("serial", request.serial);
    form.set("file", request.file, request.file.name);
    form.set("destinationPath", request.destinationPath);
    form.set("duplicatePolicy", request.duplicatePolicy);
    return this.request<TransferDto>("/api/v1/transfers/upload", { method: "POST", body: form });
  }

  public async downloadFile(request: { serial: string; sourcePath: string; destinationProfile: string; duplicatePolicy: DuplicatePolicy }): Promise<TransferDto> {
    return this.request<TransferDto>("/api/v1/transfers/download", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
    });
  }

  public async cancelTransfer(transferId: string): Promise<TransferDto> {
    return this.request<TransferDto>(`/api/v1/transfers/${encodeURIComponent(transferId)}/cancel`, { method: "POST" });
  }

  public async retryTransfer(transferId: string): Promise<TransferDto> {
    return this.request<TransferDto>(`/api/v1/transfers/${encodeURIComponent(transferId)}/retry`, { method: "POST" });
  }

  public async recordVirtualResize(sessionId: string, width: number, height: number): Promise<SessionDto> {
    return this.request<SessionDto>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/virtual-display/resize`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ width, height }),
    });
  }

  public async recordApplicationLaunch(sessionId: string, result: "sent" | "success" | "failed"): Promise<SessionDto> {
    return this.request<SessionDto>(`/api/v1/sessions/${encodeURIComponent(sessionId)}/virtual-display/application-launch`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ result }),
    });
  }

  public async getSession(sessionId: string): Promise<SessionDto> {
    return this.request<SessionDto>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`);
  }

  public async stopSession(sessionId: string, keepalive = false): Promise<SessionDto | null> {
    try {
      return await this.request<SessionDto>(`/api/v1/sessions/${encodeURIComponent(sessionId)}`, {
        method: "DELETE",
        keepalive,
      });
    } catch (error) {
      if (keepalive) return null;
      throw error;
    }
  }


  public async networkStatus(): Promise<{ active: NetworkConfigDto; url: string; restartSupported: boolean; lanEnabled: boolean }> {
    return this.request("/api/v1/network/status");
  }

  public async networkInterfaces(): Promise<{ interfaces: NetworkInterfaceDto[] }> {
    return this.request("/api/v1/network/interfaces");
  }

  public async networkConfig(): Promise<{ config: NetworkConfigDto; activeMode: string }> {
    return this.request("/api/v1/network/config");
  }

  public async validateNetworkConfig(config: NetworkConfigRequestDto): Promise<Record<string, unknown>> {
    return this.request("/api/v1/network/validate", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(config),
    });
  }

  public async applyNetworkConfig(config: NetworkConfigRequestDto): Promise<{ applied: boolean; restartRequired: boolean; restartScheduled: boolean; url: string; revokedSessions: number }> {
    return this.request("/api/v1/network/apply", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(config),
    });
  }

  public async disableNetworkAccess(currentPin: string): Promise<{ disabled: boolean; restartRequired: boolean; restartScheduled: boolean; url: string }> {
    return this.request("/api/v1/network/disable", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ currentPin }),
    });
  }

  private async request<T>(path: string, init?: RequestInit, publicRequest = false): Promise<T> {
    const method = (init?.method ?? "GET").toUpperCase();
    const headers = new Headers(init?.headers);
    if (!publicRequest && !["GET", "HEAD", "OPTIONS"].includes(method) && sharedCsrfToken) {
      headers.set("x-droidwebdisplay-csrf", sharedCsrfToken);
    }
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...init,
      headers,
      credentials: "same-origin",
    });
    const contentType = response.headers.get("content-type") ?? "";
    const payload: unknown = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok) {
      if (response.status === 401 && !publicRequest) {
        setSharedCsrfToken(null);
        globalThis.dispatchEvent?.(new CustomEvent("droidwebdisplay-auth-required"));
      }
      const message = typeof payload === "object" && payload !== null && "error" in payload
        ? String((payload as { error?: { message?: string } }).error?.message ?? response.statusText)
        : `${response.status} ${response.statusText}`;
      throw new BridgeApiError(message, response.status, payload);
    }
    return payload as T;
  }
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
  readonly firewall?: { readonly manageRule: boolean; readonly ruleName: string };
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
