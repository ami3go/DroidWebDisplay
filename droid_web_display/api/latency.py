from __future__ import annotations

import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from droid_web_display.models import SessionOptions, SessionState
from droid_web_display.scrcpy.encoder_tuning import (
    EncoderBenchmarkResult,
    configure_encoder_tuning,
    encoder_tuning_store,
    parse_h264_encoders,
    validate_encoder_name,
)


class EncoderPreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    encoder: str | None = Field(default=None, max_length=160)


class EncoderBenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    encoders: list[str] = Field(default_factory=list, max_length=6)


async def discover_h264_encoders(adb: Any, serial: str) -> list[str]:
    shell = getattr(adb, "shell", None)
    if not callable(shell):
        return []
    result = await shell(serial, "dumpsys", "media.codec", check=False, timeout=30.0)
    text = f"{getattr(result, 'stdout', '')}\n{getattr(result, 'stderr', '')}"
    return parse_h264_encoders(text)


async def device_build_fingerprint(adb: Any, serial: str) -> str | None:
    shell = getattr(adb, "shell", None)
    if not callable(shell):
        return None
    result = await shell(serial, "getprop", "ro.build.fingerprint", check=False, timeout=10.0)
    if getattr(result, "returncode", 1) != 0:
        return None
    value = str(getattr(result, "stdout", "")).strip()
    return value or None


def _active_session_for_serial(manager: Any, serial: str) -> bool:
    active_states = {
        SessionState.PROBING,
        SessionState.STARTING,
        SessionState.CREATING_DISPLAY,
        SessionState.LAUNCHING_APP,
        SessionState.CONNECTING_VIDEO,
        SessionState.CONNECTING_CONTROL,
        SessionState.RUNNING,
        SessionState.RESIZING,
    }
    return any(item.serial == serial and item.state in active_states for item in manager.list_sessions())


def install_latency_api(app: FastAPI) -> FastAPI:
    """Install low-latency encoder tuning endpoints on the existing secured API."""

    container = app.state.container
    configure_encoder_tuning(container.config.resolved_transfer_data_directory / "video-encoder-tuning.json")

    @app.get("/api/v1/devices/{serial}/video-encoders")
    async def video_encoders(serial: str, request: Request, probe: bool = False) -> dict[str, Any]:
        runtime = request.app.state.container
        await runtime.manager.select_device(serial)
        store = encoder_tuning_store()
        invalidated = False
        if probe:
            fingerprint = await device_build_fingerprint(runtime.adb, serial)
            invalidated = store.bind_device(serial, fingerprint)
            candidates = await discover_h264_encoders(runtime.adb, serial)
            store.set_discovered_encoders(serial, candidates)
        else:
            candidates = store.cached_encoders(serial)

        preference = store.preference(serial)
        return {
            "serial": serial,
            "codec": "h264",
            "encoders": candidates,
            "probed": probe,
            "preference": preference,
            # Compatibility field retained for existing clients. Automatic mode
            # no longer chooses from startup timings; only an explicit preference
            # is returned here.
            "recommended": preference,
            "benchmarks": [item.to_dict() for item in store.benchmark_results(serial)],
            "compatibleEncoders": store.compatible_encoders(serial),
            "mode": "selected" if preference else "auto",
            "automaticSelection": "scrcpy",
            "benchmarkKind": "startup-compatibility",
            "buildFingerprint": store.fingerprint(serial),
            "staleTuningInvalidated": invalidated,
            "lastInvalidation": store.last_invalidation(serial),
        }

    @app.put("/api/v1/devices/{serial}/video-encoder")
    async def set_video_encoder(serial: str, body: EncoderPreferenceRequest, request: Request) -> dict[str, Any]:
        runtime = request.app.state.container
        await runtime.manager.select_device(serial)
        encoder = validate_encoder_name(body.encoder) if body.encoder else None
        store = encoder_tuning_store()
        candidates = store.cached_encoders(serial)
        if encoder and candidates and encoder not in candidates:
            raise HTTPException(status_code=422, detail="Selected encoder was not found in the cached Android codec probe")
        store.set_preference(serial, encoder)
        return {
            "serial": serial,
            "preference": store.preference(serial),
            "recommended": store.preference(serial),
            "mode": "selected" if encoder else "auto",
            "automaticSelection": "scrcpy",
        }

    @app.post("/api/v1/devices/{serial}/video-encoders/benchmark")
    async def benchmark_video_encoders(serial: str, body: EncoderBenchmarkRequest, request: Request) -> dict[str, Any]:
        runtime = request.app.state.container
        await runtime.manager.select_device(serial)
        if _active_session_for_serial(runtime.manager, serial):
            raise HTTPException(status_code=409, detail="Disconnect the active Android session before testing video encoders")

        store = encoder_tuning_store()
        discovered = store.cached_encoders(serial)
        if not discovered:
            fingerprint = await device_build_fingerprint(runtime.adb, serial)
            store.bind_device(serial, fingerprint)
            discovered = await discover_h264_encoders(runtime.adb, serial)
            store.set_discovered_encoders(serial, discovered)

        requested = [validate_encoder_name(value) for value in body.encoders]
        candidates = requested or discovered[:4]
        if discovered:
            unknown = [value for value in candidates if value not in discovered]
            if unknown:
                raise HTTPException(status_code=422, detail=f"Encoder was not found in Android codec diagnostics: {unknown[0]}")
        if not candidates:
            raise HTTPException(status_code=422, detail="No H.264 encoder names could be discovered on this Android device")

        results: list[EncoderBenchmarkResult] = []
        for encoder in candidates[:6]:
            session = None
            started_at = time.perf_counter()
            try:
                session = await runtime.manager.start_session(
                    serial=serial,
                    options=SessionOptions(
                        video=True,
                        audio=False,
                        control=False,
                        video_codec="h264",
                        video_encoder=encoder,
                        max_size=1280,
                        video_bit_rate=8_000_000,
                        max_fps=60,
                    ),
                )
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                results.append(EncoderBenchmarkResult(encoder=encoder, success=True, startup_ms=elapsed_ms))
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started_at) * 1000.0
                results.append(
                    EncoderBenchmarkResult(
                        encoder=encoder,
                        success=False,
                        startup_ms=elapsed_ms,
                        error=str(exc)[:500],
                    )
                )
            finally:
                if session is not None:
                    try:
                        await runtime.manager.stop_session(session.session_id, reason="encoder_compatibility_test")
                    except Exception:
                        pass

        store.set_benchmark_results(serial, results)
        preference = store.preference(serial)
        return {
            "serial": serial,
            "codec": "h264",
            "benchmarks": [item.to_dict() for item in results],
            "compatibleEncoders": store.compatible_encoders(serial),
            "preference": preference,
            "recommended": preference,
            "automaticSelection": "scrcpy",
            "benchmarkKind": "startup-compatibility",
            "note": "This is a compatibility/startup test only. Startup time is not used to rank interactive latency; Auto leaves encoder selection to scrcpy.",
        }

    return app
