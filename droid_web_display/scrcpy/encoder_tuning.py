from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ENCODER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$")
_CODEC_NAME_RE = re.compile(r"\b(?:OMX|c2)\.[A-Za-z0-9._-]+", re.IGNORECASE)


@dataclass(frozen=True)
class EncoderBenchmarkResult:
    encoder: str
    success: bool
    startup_ms: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "encoder": self.encoder,
            "success": self.success,
            "startupMs": round(self.startup_ms, 1) if self.startup_ms is not None else None,
            "error": self.error,
        }


def validate_encoder_name(value: str) -> str:
    value = value.strip()
    if not _ENCODER_NAME_RE.fullmatch(value):
        raise ValueError("video encoder contains unsupported characters")
    return value


def parse_h264_encoders(text: str) -> list[str]:
    """Extract likely AVC/H.264 encoder component names from Android codec diagnostics."""

    candidates: set[str] = set()
    for match in _CODEC_NAME_RE.finditer(text):
        name = match.group(0).rstrip(".,:;)")
        lowered = name.lower()
        if "encoder" not in lowered:
            continue
        if "avc" not in lowered and "h264" not in lowered:
            continue
        try:
            candidates.add(validate_encoder_name(name))
        except ValueError:
            continue

    def rank(name: str) -> tuple[int, str]:
        lowered = name.lower()
        software = any(token in lowered for token in ("c2.android", "omx.google", "software", ".sw."))
        return (1 if software else 0, lowered)

    return sorted(candidates, key=rank)


class EncoderTuningStore:
    """Persist explicit encoder choice and compatibility evidence per Android build.

    Startup time is intentionally *not* used as an automatic latency ranking.
    Starting a scrcpy session includes ADB/JAR/tunnel work, so it is useful for
    compatibility validation but is not a trustworthy proxy for capture/encode
    latency. Auto mode therefore remains scrcpy auto unless the user explicitly
    selects an encoder.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._state: dict[str, Any] = {"schemaVersion": 2, "devices": {}}
        self._load()

    def configure(self, path: Path) -> None:
        with self._lock:
            self.path = path.resolve()
            self._state = {"schemaVersion": 2, "devices": {}}
            self._load()

    def bind_device(self, serial: str, fingerprint: str | None) -> bool:
        """Bind cached tuning to a build fingerprint.

        Returns True when stale tuning was invalidated because the Android build
        changed. Empty fingerprints are ignored so temporary ADB property errors
        do not erase a valid manual choice.
        """

        if not fingerprint:
            return False
        with self._lock:
            device = self._device(serial)
            previous = device.get("fingerprint")
            if isinstance(previous, str) and previous and previous != fingerprint:
                self._state.setdefault("devices", {})[serial] = {
                    "fingerprint": fingerprint,
                    "preference": None,
                    "encoders": [],
                    "benchmarks": [],
                    "lastInvalidation": "android-build-changed",
                    "invalidatedAt": time.time(),
                }
                self._save()
                return True
            if previous != fingerprint:
                device["fingerprint"] = fingerprint
                self._save()
            return False

    def fingerprint(self, serial: str) -> str | None:
        with self._lock:
            value = self._device(serial).get("fingerprint")
            return value if isinstance(value, str) and value else None

    def preference(self, serial: str) -> str | None:
        with self._lock:
            value = self._device(serial).get("preference")
            return value if isinstance(value, str) and value else None

    def set_preference(self, serial: str, encoder: str | None) -> None:
        with self._lock:
            device = self._device(serial)
            device["preference"] = validate_encoder_name(encoder) if encoder else None
            if encoder:
                device.pop("lastInvalidation", None)
                device.pop("invalidatedAt", None)
            self._save()

    def invalidate_preference(self, serial: str, *, expected: str | None = None, reason: str) -> bool:
        with self._lock:
            device = self._device(serial)
            current = device.get("preference")
            if not isinstance(current, str) or not current:
                return False
            if expected is not None and current != expected:
                return False
            device["preference"] = None
            device["lastInvalidation"] = reason
            device["invalidatedAt"] = time.time()
            self._save()
            return True

    def cached_encoders(self, serial: str) -> list[str]:
        with self._lock:
            raw = self._device(serial).get("encoders", [])
            if not isinstance(raw, list):
                return []
            values: list[str] = []
            for value in raw:
                if not isinstance(value, str):
                    continue
                try:
                    values.append(validate_encoder_name(value))
                except ValueError:
                    continue
            return values

    def set_discovered_encoders(self, serial: str, encoders: list[str]) -> None:
        normalized: list[str] = []
        seen: set[str] = set()
        for encoder in encoders:
            value = validate_encoder_name(encoder)
            if value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        with self._lock:
            device = self._device(serial)
            device["encoders"] = normalized
            device["probedAt"] = time.time()
            self._save()

    def benchmark_results(self, serial: str) -> list[EncoderBenchmarkResult]:
        with self._lock:
            raw = self._device(serial).get("benchmarks", [])
            results: list[EncoderBenchmarkResult] = []
            if not isinstance(raw, list):
                return results
            for item in raw:
                if not isinstance(item, dict) or not isinstance(item.get("encoder"), str):
                    continue
                results.append(
                    EncoderBenchmarkResult(
                        encoder=item["encoder"],
                        success=bool(item.get("success")),
                        startup_ms=float(item["startupMs"]) if item.get("startupMs") is not None else None,
                        error=str(item["error"]) if item.get("error") else None,
                    )
                )
            return results

    def set_benchmark_results(self, serial: str, results: list[EncoderBenchmarkResult]) -> None:
        with self._lock:
            device = self._device(serial)
            device["benchmarks"] = [result.to_dict() for result in results]
            device["compatibilityTestedAt"] = time.time()
            self._save()

    def compatible_encoders(self, serial: str) -> list[str]:
        return [result.encoder for result in self.benchmark_results(serial) if result.success]

    def recommended(self, serial: str) -> str | None:
        """Return only an explicit user preference.

        Kept for compatibility with the existing session manager API. Automatic
        selection from startup timings was removed because it optimized the
        wrong metric.
        """

        return self.preference(serial)

    def last_invalidation(self, serial: str) -> str | None:
        with self._lock:
            value = self._device(serial).get("lastInvalidation")
            return value if isinstance(value, str) and value else None

    def _device(self, serial: str) -> dict[str, Any]:
        devices = self._state.setdefault("devices", {})
        if not isinstance(devices, dict):
            devices = {}
            self._state["devices"] = devices
        value = devices.setdefault(serial, {})
        if not isinstance(value, dict):
            value = {}
            devices[serial] = value
        return value

    def _load(self) -> None:
        if self.path is None or not self.path.is_file():
            return
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(value, dict) and isinstance(value.get("devices", {}), dict):
            value["schemaVersion"] = 2
            self._state = value

    def _save(self) -> None:
        if self.path is None:
            return
        self._state["schemaVersion"] = 2
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)


_STORE = EncoderTuningStore()


def configure_encoder_tuning(path: Path) -> EncoderTuningStore:
    _STORE.configure(path)
    return _STORE


def encoder_tuning_store() -> EncoderTuningStore:
    return _STORE
