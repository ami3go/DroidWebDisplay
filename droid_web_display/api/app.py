from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import json
import secrets
import time
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, WebSocket
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.websockets import WebSocketState

from droid_web_display import __version__
from droid_web_display.auth import (
    AUTH_COOKIE_NAME,
    CSRF_HEADER_NAME,
    AuthError,
    AuthService,
    TRUST_DURATIONS,
)
from droid_web_display.adb.client import AdbClient
from droid_web_display.config import BridgeConfig
from droid_web_display.errors import BridgeError
from droid_web_display.network_access import (
    FirewallManager,
    FirewallSettings,
    LAN_HTTPS,
    LOCAL_ONLY,
    NetworkAccessConfig,
    NetworkAccessError,
    NetworkConfigStore,
    NetworkPolicy,
    TlsSettings,
    generate_certificate,
    list_network_interfaces,
    validate_certificate_pair,
)
from droid_web_display.models import (
    ChannelName,
    DisplayImePolicy,
    DisplayMode,
    SessionOptions,
    SessionState,
    VirtualDisplayOptions,
    VirtualDisplaySizeMode,
    VIRTUAL_DISPLAY_PROFILES,
)
from droid_web_display.scrcpy.artifact import ScrcpyArtifact
from droid_web_display.scrcpy.session import SessionManager
from droid_web_display.scrcpy.virtual_display import (
    apply_device_virtual_display_compatibility,
    virtual_display_capabilities,
)
from droid_web_display.transfers import AdbSyncClient, AutoDownloadConfig, AutoDownloadMonitor, DuplicatePolicy, TransferManager
from droid_web_display.transfers.paths import storage_root_list
from droid_web_display.websocket import relay_control_websocket, relay_media_websocket


class AuthSetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pin: str = Field(min_length=4, max_length=12)
    confirm_pin: str = Field(alias="confirmPin", min_length=4, max_length=12)
    duration: str = "browser-session"
    custom_seconds: int | None = Field(default=None, alias="customSeconds")
    label: str | None = Field(default=None, max_length=80)


class AuthLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pin: str = Field(min_length=4, max_length=12)
    duration: str = "browser-session"
    custom_seconds: int | None = Field(default=None, alias="customSeconds")
    label: str | None = Field(default=None, max_length=80)


class AuthPinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pin: str = Field(min_length=4, max_length=12)


class AuthChangePinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    current_pin: str = Field(alias="currentPin", min_length=4, max_length=12)
    new_pin: str = Field(alias="newPin", min_length=4, max_length=12)
    confirm_pin: str = Field(alias="confirmPin", min_length=4, max_length=12)


class VirtualDisplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    profile_id: str = Field(default="chatgpt-desktop", alias="profileId")
    size_mode: VirtualDisplaySizeMode = Field(default=VirtualDisplaySizeMode.FIXED, alias="sizeMode")
    width: int = Field(default=1600, ge=640, le=3840)
    height: int = Field(default=900, ge=480, le=2160)
    dpi: int = Field(default=240, ge=120, le=640)
    start_app: str = Field(default="com.openai.chatgpt", alias="startApp", max_length=255)
    force_stop_before_launch: bool = Field(default=False, alias="forceStopBeforeLaunch")
    keep_active: bool = Field(default=True, alias="keepActive")
    system_decorations: bool = Field(default=True, alias="systemDecorations")
    destroy_content_on_close: bool = Field(default=True, alias="destroyContentOnClose")
    ime_policy: DisplayImePolicy = Field(default=DisplayImePolicy.LOCAL, alias="imePolicy")
    preserve_aspect_ratio: bool = Field(default=True, alias="preserveAspectRatio")

    def to_options(self) -> VirtualDisplayOptions:
        value = VirtualDisplayOptions(
            profile_id=self.profile_id,
            size_mode=self.size_mode,
            width=self.width,
            height=self.height,
            dpi=self.dpi,
            start_app=self.start_app,
            force_stop_before_launch=self.force_stop_before_launch,
            keep_active=self.keep_active,
            system_decorations=self.system_decorations,
            destroy_content_on_close=self.destroy_content_on_close,
            ime_policy=self.ime_policy,
            preserve_aspect_ratio=self.preserve_aspect_ratio,
        )
        value.validate()
        return value


class StartSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    serial: str | None = None
    display_name: str | None = Field(default=None, alias="displayName", max_length=80)
    video: bool = True
    audio: bool = False
    control: bool = True
    audio_codec: str = Field(default="opus", alias="audioCodec", pattern="^(opus|aac|flac|raw)$")
    audio_bit_rate: int = Field(default=128_000, alias="audioBitRate", ge=16_000, le=512_000)
    video_codec: str = Field(default="h264", alias="videoCodec")
    max_size: int = Field(default=1920, alias="maxSize", ge=0, le=8192)
    video_bit_rate: int = Field(default=8_000_000, alias="videoBitRate", ge=2_000_000, le=50_000_000)
    max_fps: int = Field(default=30, alias="maxFps", ge=15, le=120)
    display_mode: DisplayMode = Field(default=DisplayMode.PHYSICAL, alias="displayMode")
    virtual_display: VirtualDisplayRequest | None = Field(default=None, alias="virtualDisplay")


class ResizeVirtualDisplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int = Field(ge=640, le=3840)
    height: int = Field(ge=480, le=2160)


class ApplicationLaunchResultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: str


class MoveRunningAppRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    task_id: int = Field(alias="taskId", ge=1)
    component_name: str = Field(alias="componentName", min_length=3, max_length=512)


class DownloadTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    serial: str
    source_path: str = Field(alias="sourcePath")
    destination_profile: str = Field(default="default-downloads", alias="destinationProfile")
    duplicate_policy: DuplicatePolicy = Field(default=DuplicatePolicy.RENAME, alias="duplicatePolicy")


class AutoDownloadConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    enabled: bool = False
    pc_to_android_enabled: bool = Field(default=False, alias="pcToAndroidEnabled")
    serial: str | None = None
    source_path: str = Field(default="/sdcard/Download", alias="sourcePath")
    destination_profile: str = Field(default="default-downloads", alias="destinationProfile")
    duplicate_policy: DuplicatePolicy = Field(default=DuplicatePolicy.RENAME, alias="duplicatePolicy")
    upload_duplicate_policy: DuplicatePolicy = Field(default=DuplicatePolicy.OVERWRITE, alias="uploadDuplicatePolicy")
    scan_interval_seconds: float = Field(default=2.0, alias="scanIntervalSeconds", ge=1.0, le=60.0)
    stability_seconds: float = Field(default=3.0, alias="stabilitySeconds", ge=1.0, le=300.0)
    stability_observations: int = Field(default=3, alias="stabilityObservations", ge=2, le=20)
    include_existing: bool = Field(default=False, alias="includeExisting")
    include_existing_pc: bool = Field(default=False, alias="includeExistingPc")
    delete_after_verified: bool = Field(default=False, alias="deleteAfterVerified")

    def to_config(self) -> AutoDownloadConfig:
        return AutoDownloadConfig(
            enabled=self.enabled,
            pc_to_android_enabled=self.pc_to_android_enabled,
            serial=self.serial,
            source_path=self.source_path,
            destination_profile=self.destination_profile,
            duplicate_policy=self.duplicate_policy,
            upload_duplicate_policy=self.upload_duplicate_policy,
            scan_interval_seconds=self.scan_interval_seconds,
            stability_seconds=self.stability_seconds,
            stability_observations=self.stability_observations,
            include_existing=self.include_existing,
            include_existing_pc=self.include_existing_pc,
            delete_after_verified=self.delete_after_verified,
        ).validate()


class NetworkConfigRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: str = Field(pattern="^(local-only|lan-https)$")
    bind_address: str = Field(default="127.0.0.1", alias="bindAddress")
    port: int = Field(default=8765, ge=1, le=65535)
    allowed_networks: list[str] = Field(default_factory=list, alias="allowedNetworks")
    hostname: str | None = Field(default=None, max_length=253)
    certificate_source: str = Field(default="generated", alias="certificateSource", pattern="^(generated|existing)$")
    certificate_path: str | None = Field(default=None, alias="certificatePath")
    private_key_path: str | None = Field(default=None, alias="privateKeyPath")
    certificate_validity_days: int = Field(default=365, alias="certificateValidityDays", ge=30, le=825)
    manage_firewall: bool = Field(default=False, alias="manageFirewall")
    current_pin: str | None = Field(default=None, alias="currentPin", min_length=4, max_length=12)


class NetworkPinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    current_pin: str = Field(alias="currentPin", min_length=4, max_length=12)


class ServiceContainer:
    def __init__(
        self,
        config: BridgeConfig,
        manager: SessionManager,
        adb: AdbClient,
        transfers: TransferManager,
        auto_download: AutoDownloadMonitor,
        auth: AuthService,
        network_store: NetworkConfigStore,
        network_policy: NetworkPolicy,
        firewall: FirewallManager,
    ) -> None:
        self.config = config
        self.manager = manager
        self.adb = adb
        self.transfers = transfers
        self.auto_download = auto_download
        self.auth = auth
        self.network_store = network_store
        self.network_policy = network_policy
        self.firewall = firewall


async def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container


def _error_response(exc: BridgeError) -> JSONResponse:
    status_map = {
        "device_not_found": 404,
        "session_not_found": 404,
        "transfer_not_found": 404,
        "device_not_ready": 409,
        "multiple_devices": 409,
        "session_conflict": 409,
        "transfer_conflict": 409,
        "transfer_validation": 422,
        "adb_unavailable": 503,
        "adb_command_failed": 502,
        "adb_sync_error": 502,
        "scrcpy_artifact_error": 503,
        "tunnel_error": 502,
    }
    return JSONResponse(
        status_code=status_map.get(exc.code, 500),
        content={"error": {"code": exc.code, "message": str(exc), "details": exc.details}},
    )


def create_app(
    *,
    config: BridgeConfig | None = None,
    manager: SessionManager | None = None,
    adb: AdbClient | None = None,
    transfers: TransferManager | None = None,
    auto_download: AutoDownloadMonitor | None = None,
    auth: AuthService | None = None,
) -> FastAPI:
    resolved_config = config or BridgeConfig(repo_root=Path(__file__).resolve().parents[2])
    resolved_config.validate()
    resolved_adb = adb or AdbClient(resolved_config.adb_executable)
    resolved_manager = manager or SessionManager(
        resolved_adb,
        artifact_loader=lambda: ScrcpyArtifact.from_repository(resolved_config.repo_root),
        monitor_interval=resolved_config.device_monitor_interval,
        maximum_sessions_per_device=resolved_config.maximum_display_sessions,
    )
    resolved_transfers = transfers or TransferManager(
        resolved_adb,
        AdbSyncClient(),
        data_directory=resolved_config.resolved_transfer_data_directory,
        destination_profiles=resolved_config.destination_profiles(),
        concurrency=resolved_config.transfer_concurrency,
        maximum_queue_length=resolved_config.maximum_transfer_queue_length,
        maximum_file_size=resolved_config.maximum_file_size,
    )

    resolved_auto_download = auto_download or AutoDownloadMonitor(
        resolved_adb,
        resolved_transfers,
        data_directory=resolved_config.resolved_transfer_data_directory,
    )
    resolved_auth = auth or AuthService(resolved_config.resolved_auth_data_file)
    active_network_config = NetworkAccessConfig(
        mode=resolved_config.network_mode,
        bind_address=resolved_config.bind_host,
        port=resolved_config.bind_port,
        allowed_networks=resolved_config.allowed_client_networks,
        hostname=resolved_config.configured_hostname,
        tls=TlsSettings(
            enabled=resolved_config.tls_enabled,
            certificate_path=str(resolved_config.tls_certificate_path) if resolved_config.tls_certificate_path else None,
            private_key_path=str(resolved_config.tls_private_key_path) if resolved_config.tls_private_key_path else None,
        ),
    ).validate(require_files=False)
    resolved_network_store = NetworkConfigStore(resolved_config.resolved_network_config_file)
    resolved_network_policy = NetworkPolicy(active_network_config)
    resolved_firewall = FirewallManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = ServiceContainer(resolved_config, resolved_manager, resolved_adb, resolved_transfers, resolved_auto_download, resolved_auth, resolved_network_store, resolved_network_policy, resolved_firewall)
        await resolved_transfers.start()
        await resolved_auto_download.start()
        try:
            yield
        finally:
            await resolved_auto_download.close()
            await resolved_transfers.close()
            await resolved_manager.close()

    app = FastAPI(
        title="DroidWebDisplay Local Service",
        version=__version__,
        docs_url="/api/v1/docs",
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    app.state.container = ServiceContainer(resolved_config, resolved_manager, resolved_adb, resolved_transfers, resolved_auto_download, resolved_auth, resolved_network_store, resolved_network_policy, resolved_firewall)

    public_auth_paths = {
        "/api/v1/auth/status",
        "/api/v1/auth/setup",
        "/api/v1/auth/login",
    }
    unsafe_methods = {"POST", "PUT", "PATCH", "DELETE"}

    def auth_payload(session: dict | None) -> dict:
        return {
            "configured": resolved_auth.configured,
            "authenticated": session is not None,
            "trustModel": "pc-local",
            "phoneAuthoritative": False,
            "csrfToken": resolved_auth.csrf_token(session["sessionId"]) if session else None,
            "currentSession": session,
            "durationChoices": [*TRUST_DURATIONS, "custom"],
            "customDuration": {"minimumSeconds": 300, "maximumSeconds": 315360000},
            "networkAccess": {
                "mode": active_network_config.mode,
                "secure": active_network_config.mode == LAN_HTTPS,
                "url": active_network_config.primary_url,
            },
        }

    def set_auth_cookie(response: Response, token: str, max_age: int | None) -> None:
        response.set_cookie(
            AUTH_COOKIE_NAME,
            token,
            max_age=max_age,
            httponly=True,
            samesite="strict",
            secure=active_network_config.mode == LAN_HTTPS,
            path="/",
        )

    def clear_auth_cookie(response: Response) -> None:
        response.delete_cookie(AUTH_COOKIE_NAME, path="/", samesite="strict", secure=active_network_config.mode == LAN_HTTPS)

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        client_host = request.client.host if request.client else None
        if not resolved_network_policy.client_allowed(client_host):
            resolved_auth.audit_event("client-network-rejected", clientIp=client_host)
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "client_network_rejected", "message": "Client address is outside the configured network allowlist"}},
            )
        if client_host != "testclient" and not resolved_network_policy.host_allowed(request.headers.get("host")):
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "host_rejected", "message": "Host header is not approved"}},
            )
        if request.method in unsafe_methods and not resolved_network_policy.origin_allowed(request.headers.get("origin")):
            return JSONResponse(
                status_code=403,
                content={"error": {"code": "origin_rejected", "message": "Cross-origin request rejected"}},
            )
        if resolved_config.authentication_required and path.startswith("/api/v1") and path not in public_auth_paths:
            session = resolved_auth.authenticate(request.cookies.get(AUTH_COOKIE_NAME))
            if session is None:
                return JSONResponse(
                    status_code=401,
                    content={"error": {"code": "authentication_required", "message": "PIN authentication is required"}},
                )
            request.state.auth_session = session
            if request.method in unsafe_methods and not resolved_auth.csrf_valid(session["sessionId"], request.headers.get(CSRF_HEADER_NAME)):
                return JSONResponse(
                    status_code=403,
                    content={"error": {"code": "csrf_rejected", "message": "CSRF token is missing or invalid"}},
                )
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'sha256-0u7HdijpKCtbMJSF/CxBDiwEw6/NSTMjgCYEMe9Byl0='; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        if path.startswith("/api/v1/auth"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(BridgeError)
    async def bridge_error_handler(_: Request, exc: BridgeError) -> JSONResponse:
        return _error_response(exc)

    @app.exception_handler(AuthError)
    async def auth_error_handler(_: Request, exc: AuthError) -> JSONResponse:
        status = {
            "invalid_pin": 401,
            "not_configured": 409,
            "already_configured": 409,
            "pin_validation": 422,
            "duration_validation": 422,
            "rate_limited": 429,
        }.get(exc.code, 400)
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
        return JSONResponse(
            status_code=status,
            headers=headers,
            content={"error": {"code": exc.code, "message": str(exc), "retryAfter": exc.retry_after}},
        )

    @app.exception_handler(NetworkAccessError)
    async def network_access_error_handler(_: Request, exc: NetworkAccessError) -> JSONResponse:
        status = 422 if exc.code.startswith("network_") else 400
        return JSONResponse(status_code=status, content={"error": {"code": exc.code, "message": str(exc)}})

    @app.get("/api/v1/auth/status")
    async def auth_status(request: Request) -> dict:
        session = resolved_auth.authenticate(request.cookies.get(AUTH_COOKIE_NAME))
        return auth_payload(session)

    @app.post("/api/v1/auth/setup", status_code=201)
    async def auth_setup(body: AuthSetupRequest, request: Request, response: Response) -> dict:
        if body.pin != body.confirm_pin:
            raise AuthError("PIN confirmation does not match", code="pin_validation")
        grant = resolved_auth.setup(
            body.pin,
            duration=body.duration,
            custom_seconds=body.custom_seconds,
            user_agent=request.headers.get("user-agent", "Unknown browser"),
            label=body.label,
            client_ip=request.client.host if request.client else None,
            access_mode="lan" if active_network_config.mode == LAN_HTTPS else "local",
        )
        set_auth_cookie(response, grant.token, grant.cookie_max_age)
        return auth_payload(grant.session)

    @app.post("/api/v1/auth/login")
    async def auth_login(body: AuthLoginRequest, request: Request, response: Response) -> dict:
        grant = resolved_auth.login(
            body.pin,
            duration=body.duration,
            custom_seconds=body.custom_seconds,
            user_agent=request.headers.get("user-agent", "Unknown browser"),
            client_key=request.client.host if request.client else "loopback",
            label=body.label,
            client_ip=request.client.host if request.client else None,
            access_mode="lan" if active_network_config.mode == LAN_HTTPS else "local",
        )
        set_auth_cookie(response, grant.token, grant.cookie_max_age)
        return auth_payload(grant.session)

    @app.post("/api/v1/auth/logout")
    async def auth_logout(request: Request, response: Response) -> dict:
        session = request.state.auth_session
        resolved_auth.logout(session["sessionId"])
        clear_auth_cookie(response)
        return {"authenticated": False, "status": "logged-out"}

    @app.get("/api/v1/auth/sessions")
    async def auth_sessions(request: Request) -> dict:
        session = request.state.auth_session
        return {"sessions": resolved_auth.list_sessions(session["sessionId"]), "trustModel": "pc-local"}

    @app.delete("/api/v1/auth/sessions/{session_id}")
    async def auth_revoke_session(session_id: str, request: Request, response: Response) -> dict:
        current = request.state.auth_session
        revoked = resolved_auth.revoke(session_id, actor_session_id=current["sessionId"])
        if session_id == current["sessionId"]:
            clear_auth_cookie(response)
        return {"revoked": revoked, "sessionId": session_id, "currentSessionRevoked": session_id == current["sessionId"]}

    @app.post("/api/v1/auth/sessions/revoke-all")
    async def auth_revoke_all(body: AuthPinRequest, request: Request, response: Response) -> dict:
        current = request.state.auth_session
        count = resolved_auth.revoke_all(body.pin, actor_session_id=current["sessionId"])
        clear_auth_cookie(response)
        return {"revoked": count, "authenticated": False}

    @app.post("/api/v1/auth/change-pin")
    async def auth_change_pin(body: AuthChangePinRequest, request: Request, response: Response) -> dict:
        if body.new_pin != body.confirm_pin:
            raise AuthError("PIN confirmation does not match", code="pin_validation")
        current = request.state.auth_session
        resolved_auth.change_pin(body.current_pin, body.new_pin, actor_session_id=current["sessionId"])
        clear_auth_cookie(response)
        return {"changed": True, "authenticated": False, "sessionsRevoked": True}

    @app.get("/api/v1/auth/audit")
    async def auth_audit(limit: int = Query(default=100, ge=1, le=500)) -> dict:
        return {"events": resolved_auth.audit_events(limit), "sensitiveValuesLogged": False}

    @app.get("/api/v1/health")
    async def health(container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        try:
            adb_version = await container.adb.version()
            adb_status = "available"
        except BridgeError as exc:
            adb_version = None
            adb_status = exc.code
        sessions = container.manager.list_sessions()
        transfers_values = container.transfers.list_records()
        return {
            "status": "ok" if adb_status == "available" else "degraded",
            "phase": 9,
            "version": __version__,
            "bind": f"{container.config.bind_host}:{container.config.bind_port}",
            "adb": {"status": adb_status, "version": adb_version},
            "sessions": {
                "total": len(sessions),
                "active": sum(item.state.value in {"starting", "running"} for item in sessions),
            },
            "transfers": {
                "total": len(transfers_values),
                "active": sum(item.state.value in {"queued", "preparing", "transferring", "verifying"} for item in transfers_values),
            },
        }

    @app.get("/api/v1/version")
    async def version() -> dict:
        return {
            "version": __version__,
            "phase": 9,
            "scrcpyVersion": "4.1",
            "adapter": "scrcpy-4.1",
            "apiVersion": "v1",
            "transferEngine": "adb-sync-v1",
            "displayEngine": "scrcpy-v4.1-new-display",
        }

    @app.get("/api/v1/browser-support")
    async def browser_support() -> dict:
        return {
            "engine": "Chromium",
            "required": ["WebSocket", "ReadableStream", "WritableStream", "VideoDecoder", "EncodedVideoChunk"],
            "optionalAudio": ["AudioDecoder", "EncodedAudioChunk", "AudioContext"],
            "videoCodec": "h264",
            "audioCodec": "opus",
            "softwareDecoderFallback": False,
        }

    @app.get("/api/v1/devices")
    async def devices(container: Annotated[ServiceContainer, Depends(get_container)], enrich: bool = Query(default=True)) -> dict:
        values = await container.manager.list_devices(enrich=enrich)
        return {"devices": [item.to_dict() for item in values]}

    @app.get("/api/v1/devices/{serial}/virtual-display-capabilities")
    async def virtual_display_probe(
        serial: str,
        container: Annotated[ServiceContainer, Depends(get_container)],
        start_app: str = Query(default="com.openai.chatgpt", alias="startApp"),
    ) -> dict:
        device = await container.manager.select_device(serial)
        package_installed: bool | None = None
        supported_codecs = ["h264"]
        if start_app:
            package_installed = await container.adb.package_installed(serial, start_app)
        try:
            supported_codecs = await container.adb.supported_video_codecs(serial)
        except BridgeError:
            pass
        return virtual_display_capabilities(
            device,
            supported_codecs=supported_codecs,
            requested_package=start_app or None,
            package_installed=package_installed,
        )

    @app.get("/api/v1/devices/{serial}/apps")
    async def installed_apps(
        serial: str,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        await container.manager.select_device(serial)
        apps = await container.adb.list_launchable_apps(serial)
        return {
            "apps": [
                {
                    **item,
                    "secondaryDisplayCompatibility": "unknown",
                }
                for item in apps
            ]
        }

    @app.get("/api/v1/devices/{serial}/running-apps")
    async def running_apps(
        serial: str,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        await container.manager.select_device(serial)
        values = await container.adb.list_running_gui_apps(serial)
        return {
            "serial": serial,
            "apps": [item.to_dict() for item in values],
            "moveStrategy": "start-activity-on-display",
        }

    @app.get("/api/v1/virtual-display-profiles")
    async def virtual_display_profiles() -> dict:
        return {
            "profiles": [
                {
                    **profile.to_dict(),
                    "videoCodec": "h264",
                    "videoBitRate": 6_000_000 if key == "low-bandwidth" else (16_000_000 if key in {"full-hd-desktop", "flexible-window"} else 12_000_000),
                    "maxFps": 30 if key == "low-bandwidth" else 60,
                }
                for key, profile in VIRTUAL_DISPLAY_PROFILES.items()
            ]
        }

    @app.get("/api/v1/sessions")
    async def sessions(container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return {"sessions": [item.to_dict() for item in container.manager.list_sessions()]}

    @app.post("/api/v1/sessions", status_code=201)
    async def create_session(body: StartSessionRequest, container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        try:
            requested_virtual_options = body.virtual_display.to_options() if body.virtual_display else None
            effective_virtual_options = requested_virtual_options
            compatibility_warnings: list[str] = []
            ime_fallback_applied = False
            selected = None
            if body.display_mode == DisplayMode.VIRTUAL:
                selected = await container.manager.select_device(body.serial)
                if (selected.sdk or 0) < 29:
                    raise HTTPException(status_code=422, detail="Virtual Display mode requires Android API 29 or newer")
                assert requested_virtual_options is not None
                if requested_virtual_options.start_app and not await container.adb.package_installed(
                    selected.serial, requested_virtual_options.start_app
                ):
                    raise HTTPException(
                        status_code=422,
                        detail=f"Application is not installed on the connected device: {requested_virtual_options.start_app}",
                    )
                effective_virtual_options, compatibility_warnings, ime_fallback_applied = (
                    apply_device_virtual_display_compatibility(selected, requested_virtual_options)
                )

            options = SessionOptions(
                video=body.video,
                audio=body.audio,
                control=body.control,
                audio_codec=body.audio_codec,
                audio_bit_rate=body.audio_bit_rate,
                video_codec=body.video_codec,
                max_size=body.max_size,
                video_bit_rate=body.video_bit_rate,
                max_fps=body.max_fps,
                display_mode=body.display_mode,
                virtual_display=effective_virtual_options,
            )
            options.validate()
            session = await container.manager.start_session(
                serial=selected.serial if selected else body.serial,
                options=options,
                display_name=body.display_name,
            )
            if requested_virtual_options and effective_virtual_options:
                session.requested_ime_policy = requested_virtual_options.ime_policy.value
                session.effective_ime_policy = effective_virtual_options.ime_policy.value
                session.ime_policy_fallback_applied = ime_fallback_applied
                session.virtual_display_warnings.extend(compatibility_warnings)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return session.to_dict()

    @app.get("/api/v1/sessions/{session_id}")
    async def get_session(session_id: str, container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return container.manager.get_session(session_id).to_dict()

    @app.delete("/api/v1/sessions/{session_id}")
    async def delete_session(session_id: str, container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return (await container.manager.stop_session(session_id)).to_dict()

    @app.get("/api/v1/devices/{serial}/sessions")
    async def device_sessions(
        serial: str,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        # Validate the device explicitly so a typo cannot silently look like an
        # empty session list. Only active/indexed sessions belong in display tabs.
        await container.manager.select_device(serial)
        values = container.manager.list_sessions_for_device(serial)
        capacity = container.manager.session_capacity(serial)
        return {
            "serial": serial,
            "activeSessionCount": len(values),
            "maximumSessions": capacity["maximumSessions"],
            "availableSlots": capacity["availableSlots"],
            "sessions": [item.to_dict() for item in values],
        }

    @app.get("/api/v1/devices/{serial}/display-diagnostics")
    async def device_display_diagnostics(
        serial: str,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        await container.manager.select_device(serial)
        values = container.manager.list_sessions_for_device(serial)
        capacity = container.manager.session_capacity(serial)
        now = time.time()
        displays = []
        for session in values:
            payload = session.to_dict()
            started = session.started_at or session.created_at
            displays.append({
                "sessionId": session.session_id,
                "state": session.state.value,
                "display": payload["display"],
                "createdAt": session.created_at,
                "startedAt": session.started_at,
                "ageSeconds": max(0.0, now - started),
                "channelDiagnostics": payload["channelDiagnostics"],
                "error": session.error,
                "stopReason": session.stop_reason,
                "virtualDisplay": payload["virtualDisplay"],
            })
        return {
            "serial": serial,
            "capacity": capacity,
            "displays": displays,
        }

    @app.post("/api/v1/devices/{serial}/sessions", status_code=201)
    async def create_device_session(
        serial: str,
        body: StartSessionRequest,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        if body.serial is not None and body.serial != serial:
            raise HTTPException(
                status_code=422,
                detail="Body serial must match the device serial in the request path",
            )
        scoped_body = body.model_copy(update={"serial": serial})
        return await create_session(scoped_body, container)

    @app.delete("/api/v1/devices/{serial}/sessions/{session_id}")
    async def delete_device_session(
        serial: str,
        session_id: str,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        session = container.manager.get_session(session_id)
        if session.serial != serial:
            raise HTTPException(status_code=404, detail="Session not found for this device")
        return (await container.manager.stop_session(session_id)).to_dict()

    @app.delete("/api/v1/devices/{serial}/sessions")
    async def delete_device_sessions(
        serial: str,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        # Snapshot before stopping because stop_session removes each session from
        # the per-device active index. Sequential cleanup keeps ADB resource
        # release deterministic and isolates failures to the session being closed.
        values = list(container.manager.list_sessions_for_device(serial))
        stopped: list[dict] = []
        for session in values:
            stopped.append((await container.manager.stop_session(session.session_id)).to_dict())
        return {
            "serial": serial,
            "stoppedCount": len(stopped),
            "sessions": stopped,
        }

    @app.post("/api/v1/sessions/{session_id}/virtual-display/resize")
    async def record_virtual_resize(
        session_id: str,
        body: ResizeVirtualDisplayRequest,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        return container.manager.record_virtual_resize(session_id, body.width, body.height).to_dict()

    @app.post("/api/v1/sessions/{session_id}/virtual-display/move-running-app")
    async def move_running_app(
        session_id: str,
        body: MoveRunningAppRequest,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        session = container.manager.get_session(session_id)
        if session.state != SessionState.RUNNING:
            raise HTTPException(status_code=409, detail=f"Session is {session.state.value}")
        if session.options.display_mode != DisplayMode.VIRTUAL or session.display_id is None:
            raise HTTPException(status_code=409, detail="A running virtual-display session is required")

        running = await container.adb.list_running_gui_apps(session.serial)
        selected = next(
            (item for item in running if item.task_id == body.task_id and item.component_name == body.component_name),
            None,
        )
        if selected is None:
            raise HTTPException(status_code=404, detail="The selected Android GUI task is no longer running")
        if selected.display_id == session.display_id:
            session.application = selected.package_name
            return {
                "status": "already-on-target",
                "moved": False,
                "verified": True,
                "sessionId": session_id,
                "displayId": session.display_id,
                "app": selected.to_dict(),
                "strategy": "none",
            }

        try:
            command = await container.adb.move_running_app_to_display(
                session.serial,
                task_id=selected.task_id,
                component_name=selected.component_name,
                display_id=session.display_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        await asyncio.sleep(0.5)
        refreshed = await container.adb.list_running_gui_apps(session.serial)
        after = next(
            (
                item
                for item in refreshed
                if item.display_id == session.display_id
                and (item.task_id == selected.task_id or item.component_name == selected.component_name)
            ),
            None,
        )
        if after is not None:
            session.application = after.package_name
        return {
            "status": "moved" if after else "launch-sent-unverified",
            "moved": True,
            "verified": after is not None,
            "sessionId": session_id,
            "displayId": session.display_id,
            "app": (after or selected).to_dict(),
            **command,
        }

    @app.post("/api/v1/sessions/{session_id}/virtual-display/application-launch")
    async def record_application_launch(
        session_id: str,
        body: ApplicationLaunchResultRequest,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        try:
            return container.manager.mark_application_launch(session_id, body.result).to_dict()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/v1/storage/android-roots")
    async def android_storage_roots(
        container: Annotated[ServiceContainer, Depends(get_container)],
        serial: str | None = Query(default=None),
    ) -> dict:
        roots = storage_root_list()
        selected_serial = serial
        if not selected_serial:
            devices = await container.manager.list_devices(enrich=False)
            ready = [item for item in devices if item.ready]
            if len(ready) == 1:
                selected_serial = ready[0].serial
        discover = getattr(container.adb, "external_storage_roots", None)
        if selected_serial and callable(discover):
            try:
                roots.extend(await discover(selected_serial))
            except BridgeError:
                pass
        return {"roots": roots, "defaultPath": "/sdcard/Download"}

    @app.get("/api/v1/auto-download")
    async def auto_download_get(container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return container.auto_download.snapshot()

    @app.put("/api/v1/auto-download")
    async def auto_download_put(
        body: AutoDownloadConfigRequest,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        return await container.auto_download.configure(body.to_config())

    @app.post("/api/v1/auto-download/scan")
    async def auto_download_scan(container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return await container.auto_download.scan_now()

    @app.post("/api/v1/auto-download/reset")
    async def auto_download_reset(container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return await container.auto_download.clear_history()

    @app.get("/api/v1/storage/android")
    async def android_storage(
        container: Annotated[ServiceContainer, Depends(get_container)],
        serial: str = Query(..., min_length=1),
        path: str = Query(default="/sdcard/Download"),
    ) -> dict:
        entries = await container.transfers.list_android(serial, path)
        return {"path": path, "entries": [entry.to_dict() for entry in entries]}

    @app.get("/api/v1/destination-profiles")
    async def destination_profiles(container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return {"profiles": container.transfers.destination_profile_list()}

    @app.post("/api/v1/destination-profiles/{profile_id}/open")
    async def destination_profile_open(profile_id: str, container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        path = container.transfers.open_destination_profile(profile_id)
        return {"profileId": profile_id, "path": str(path), "opened": True}

    @app.get("/api/v1/transfers")
    async def transfer_list(container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return {"transfers": [item.to_dict() for item in container.transfers.list_records()]}

    @app.get("/api/v1/transfers/{transfer_id}")
    async def transfer_get(transfer_id: str, container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return container.transfers.get(transfer_id).to_dict()

    @app.post("/api/v1/transfers/upload", status_code=202)
    async def transfer_upload(
        container: Annotated[ServiceContainer, Depends(get_container)],
        file: UploadFile = File(...),
        serial: str = Form(...),
        destination_path: str = Form(default="/sdcard/Download/DroidWebDisplayInbox", alias="destinationPath"),
        duplicate_policy: DuplicatePolicy = Form(default=DuplicatePolicy.RENAME, alias="duplicatePolicy"),
    ) -> dict:
        try:
            spool, size, safe_name = await container.transfers.spool_upload(file.filename or "file", file)
        finally:
            await file.close()
        record = await container.transfers.enqueue_upload(
            serial=serial,
            spool_path=spool,
            original_filename=safe_name,
            size=size,
            destination_directory=destination_path,
            duplicate_policy=duplicate_policy,
        )
        return record.to_dict()

    @app.post("/api/v1/transfers/download", status_code=202)
    async def transfer_download(
        body: DownloadTransferRequest,
        container: Annotated[ServiceContainer, Depends(get_container)],
    ) -> dict:
        record = await container.transfers.enqueue_download(
            serial=body.serial,
            source_path=body.source_path,
            destination_profile=body.destination_profile,
            duplicate_policy=body.duplicate_policy,
        )
        return record.to_dict()

    @app.post("/api/v1/transfers/{transfer_id}/cancel")
    async def transfer_cancel(transfer_id: str, container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return (await container.transfers.cancel(transfer_id)).to_dict()

    @app.post("/api/v1/transfers/{transfer_id}/retry", status_code=202)
    async def transfer_retry(transfer_id: str, container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return (await container.transfers.retry(transfer_id)).to_dict()

    def network_config_from_request(body: NetworkConfigRequest, *, generate: bool) -> tuple[NetworkAccessConfig, dict[str, Any] | None]:
        if body.mode == LOCAL_ONLY:
            return NetworkAccessConfig(mode=LOCAL_ONLY, bind_address="127.0.0.1", port=body.port), None
        certificate_path: Path
        private_key_path: Path
        certificate_info: dict[str, Any] | None
        if body.certificate_source == "generated":
            certificate_path = resolved_config.resolved_transfer_data_directory / "tls" / "droidwebdisplay-cert.pem"
            private_key_path = resolved_config.resolved_transfer_data_directory / "tls" / "droidwebdisplay-key.pem"
            certificate_info = generate_certificate(
                certificate_path,
                private_key_path,
                bind_address=body.bind_address,
                hostname=body.hostname,
                validity_days=body.certificate_validity_days,
            ) if generate else None
        else:
            if not body.certificate_path or not body.private_key_path:
                raise NetworkAccessError("Existing certificate and private-key paths are required", code="network_certificate")
            certificate_path = Path(body.certificate_path).expanduser().resolve()
            private_key_path = Path(body.private_key_path).expanduser().resolve()
            certificate_info = validate_certificate_pair(
                certificate_path,
                private_key_path,
                bind_address=body.bind_address,
                hostname=body.hostname,
            )
        config_value = NetworkAccessConfig(
            mode=LAN_HTTPS,
            bind_address=body.bind_address,
            port=body.port,
            allowed_networks=tuple(body.allowed_networks),
            hostname=body.hostname,
            tls=TlsSettings(
                enabled=True,
                certificate_path=str(certificate_path),
                private_key_path=str(private_key_path),
                certificate_source=body.certificate_source,
            ),
            firewall=FirewallSettings(manage_rule=body.manage_firewall),
        ).validate(require_files=generate or body.certificate_source == "existing")
        return config_value, certificate_info

    @app.get("/api/v1/network/status")
    async def network_status() -> dict:
        return {
            "active": active_network_config.to_dict(redact_private_key=True),
            "url": active_network_config.primary_url,
            "restartSupported": callable(getattr(app.state, "request_restart", None)),
            "lanEnabled": active_network_config.mode == LAN_HTTPS,
        }

    @app.get("/api/v1/network/interfaces")
    async def network_interfaces() -> dict:
        return {"interfaces": [item.to_dict() for item in list_network_interfaces()]}

    @app.get("/api/v1/network/config")
    async def network_config() -> dict:
        try:
            stored = resolved_network_store.load()
        except NetworkAccessError:
            stored = active_network_config
        return {"config": stored.to_dict(redact_private_key=True), "activeMode": active_network_config.mode}

    @app.post("/api/v1/network/validate")
    async def network_validate(body: NetworkConfigRequest, request: Request) -> dict:
        if not body.current_pin or not resolved_auth.verify_pin(body.current_pin):
            resolved_auth.audit_event("network-config-validation-rejected", actorSessionId=request.state.auth_session["sessionId"])
            raise AuthError("Invalid current PIN", code="invalid_pin")
        config_value, certificate_info = network_config_from_request(body, generate=False)
        resolved_auth.audit_event("network-config-validated", mode=config_value.mode, bindAddress=config_value.bind_address)
        return {
            "valid": True,
            "config": config_value.to_dict(redact_private_key=True),
            "certificate": certificate_info,
            "allowedOrigins": sorted(NetworkPolicy(config_value).allowed_origins),
        }

    @app.post("/api/v1/network/apply")
    async def network_apply(body: NetworkConfigRequest, request: Request, background_tasks: BackgroundTasks) -> dict:
        if not body.current_pin or not resolved_auth.verify_pin(body.current_pin):
            resolved_auth.audit_event("network-config-apply-rejected", actorSessionId=request.state.auth_session["sessionId"])
            raise AuthError("Invalid current PIN", code="invalid_pin")
        config_value, certificate_info = network_config_from_request(body, generate=True)
        previous = resolved_network_store.load()
        resolved_network_store.save(config_value)
        firewall_result = None
        if previous.firewall.manage_rule and (not config_value.firewall.manage_rule or previous.port != config_value.port):
            resolved_firewall.apply(previous, remove=True)
        if config_value.firewall.manage_rule:
            firewall_result = resolved_firewall.apply(config_value)
        resolved_auth.audit_event(
            "lan-access-enabled" if config_value.mode == LAN_HTTPS else "lan-access-disabled",
            bindAddress=config_value.bind_address,
            port=config_value.port,
        )
        revoked = resolved_auth.revoke_all_for_reason("network-mode-changed", actor_session_id=request.state.auth_session["sessionId"])
        restart_callback = getattr(app.state, "request_restart", None)
        if callable(restart_callback):
            background_tasks.add_task(restart_callback)
        return {
            "applied": True,
            "restartRequired": True,
            "restartScheduled": callable(restart_callback),
            "url": config_value.primary_url,
            "revokedSessions": revoked,
            "certificate": certificate_info,
            "firewall": firewall_result,
        }

    @app.post("/api/v1/network/disable")
    async def network_disable(body: NetworkPinRequest, request: Request, background_tasks: BackgroundTasks) -> dict:
        if not resolved_auth.verify_pin(body.current_pin):
            raise AuthError("Invalid current PIN", code="invalid_pin")
        previous = resolved_network_store.load()
        if previous.firewall.manage_rule:
            resolved_firewall.apply(previous, remove=True)
        local = resolved_network_store.reset_local_only(port=previous.port)
        revoked = resolved_auth.revoke_all_for_reason("lan-access-disabled", actor_session_id=request.state.auth_session["sessionId"])
        resolved_auth.audit_event("lan-access-disabled", port=local.port)
        restart_callback = getattr(app.state, "request_restart", None)
        if callable(restart_callback):
            background_tasks.add_task(restart_callback)
        return {"disabled": True, "restartRequired": True, "restartScheduled": callable(restart_callback), "url": local.primary_url, "revokedSessions": revoked}

    @app.get("/api/v1/network/certificate/public")
    async def network_public_certificate() -> FileResponse:
        stored = resolved_network_store.load()
        if stored.mode != LAN_HTTPS or not stored.tls.certificate_path:
            raise NetworkAccessError("No LAN certificate is configured", code="network_certificate")
        path = Path(stored.tls.certificate_path)
        if not path.is_file():
            raise NetworkAccessError("Configured public certificate is missing", code="network_certificate")
        return FileResponse(path, media_type="application/x-pem-file", filename="droidwebdisplay-cert.pem")

    async def close_ws(websocket: WebSocket, code: int, reason: str) -> None:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close(code=code, reason=reason)

    async def authenticate_websocket(websocket: WebSocket) -> dict | None:
        if not resolved_config.authentication_required:
            return {"sessionId": "authentication-disabled"}
        client_host = websocket.client.host if websocket.client else None
        if not resolved_network_policy.client_allowed(client_host):
            await websocket.accept()
            await close_ws(websocket, 4403, "client network rejected")
            return None
        if client_host != "testclient" and not resolved_network_policy.host_allowed(websocket.headers.get("host")):
            await websocket.accept()
            await close_ws(websocket, 4403, "host rejected")
            return None
        if not resolved_network_policy.origin_allowed(websocket.headers.get("origin")):
            await websocket.accept()
            await close_ws(websocket, 4403, "origin rejected")
            return None
        session = resolved_auth.authenticate(websocket.cookies.get(AUTH_COOKIE_NAME))
        if session is None:
            await websocket.accept()
            await close_ws(websocket, 4401, "PIN authentication required")
            return None
        return session

    @app.websocket("/ws/v1/sessions/{session_id}/{channel_name}")
    async def session_channel(websocket: WebSocket, session_id: str, channel_name: str) -> None:
        if await authenticate_websocket(websocket) is None:
            return
        container: ServiceContainer = websocket.app.state.container
        client_id = websocket.query_params.get("clientId") or secrets.token_urlsafe(8)
        try:
            channel_key = ChannelName(channel_name)
        except ValueError:
            await websocket.accept()
            await close_ws(websocket, 4404, "unknown channel")
            return
        try:
            session = container.manager.get_session(session_id)
        except BridgeError:
            await websocket.accept()
            await close_ws(websocket, 4404, "session not found")
            return
        if session.state != SessionState.RUNNING:
            await websocket.accept()
            await close_ws(websocket, 4409, f"session is {session.state.value}")
            return
        channel = session.channels.get(channel_key)
        if channel is None:
            await websocket.accept()
            await close_ws(websocket, 4404, "channel not enabled")
            return
        try:
            await channel.claim(client_id)
        except BridgeError:
            await websocket.accept()
            await close_ws(websocket, 4409, "channel already attached")
            return

        reason = "relay_ended"
        try:
            result = await (relay_control_websocket(channel, websocket) if channel_key == ChannelName.CONTROL else relay_media_websocket(channel, websocket))
            reason = result.close_reason
        finally:
            await channel.release(client_id, reason=reason)
            if session.state in {SessionState.STARTING, SessionState.RUNNING}:
                await container.manager.stop_session(session_id, reason=f"browser_{channel_key.value}_{reason}")

    @app.websocket("/ws/v1/events")
    async def events(websocket: WebSocket) -> None:
        if await authenticate_websocket(websocket) is None:
            return
        await websocket.accept()
        container: ServiceContainer = websocket.app.state.container
        previous = ""
        try:
            while True:
                payload = {
                    "type": "bridge-snapshot",
                    "phase": 9,
                    "sessions": [item.to_dict() for item in container.manager.list_sessions()],
                    "transfers": [item.to_dict() for item in container.transfers.list_records()],
                    "autoDownload": container.auto_download.snapshot(),
                }
                encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                if encoded != previous:
                    await websocket.send_json(payload)
                    previous = encoded
                await asyncio.sleep(0.5)
        except Exception:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await close_ws(websocket, 1000, "events closed")

    @app.get("/api/v1/diagnostics")
    async def diagnostics(container: Annotated[ServiceContainer, Depends(get_container)]) -> dict:
        return {
            "phase": 9,
            "protocolParsingOwner": "browser-typescript-adapter",
            "bridgeStreamRole": "opaque-binary-proxy",
            "transferEngine": "direct-adb-sync-v1",
            "transferConsoleParsing": False,
            "virtualDisplayEngine": "scrcpy-v4.1-new-display",
            "virtualDisplayControlMessages": ["START_APP", "RESIZE_DISPLAY"],
            "tunnelMode": "adb-forward",
            "channelOrder": ["video", "audio", "control"],
            "sessions": [item.to_dict() for item in container.manager.list_sessions()],
            "transfers": [item.to_dict() for item in container.transfers.list_records()],
            "autoDownload": container.auto_download.snapshot(),
        }

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        components = schema.setdefault("components", {})
        components.setdefault("securitySchemes", {})["pcLocalSession"] = {
            "type": "apiKey",
            "in": "cookie",
            "name": AUTH_COOKIE_NAME,
            "description": "Opaque PC-local trusted-session cookie. PINs and raw tokens are never logged.",
        }
        public_paths = {"/api/v1/auth/status", "/api/v1/auth/setup", "/api/v1/auth/login"}
        for path, path_item in schema.get("paths", {}).items():
            if path in public_paths:
                continue
            for operation in path_item.values():
                if isinstance(operation, dict) and "responses" in operation:
                    operation["security"] = [{"pcLocalSession": []}]
        schema.setdefault("info", {})["x-trust-model"] = "PC-local by default; optional authenticated private-LAN HTTPS; the Android phone is not the trust authority"
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    web_root = resolved_config.repo_root / "apps" / "web-client" / "dist"
    if web_root.is_dir():
        app.mount("/", StaticFiles(directory=web_root, html=True), name="web-client")

    return app
