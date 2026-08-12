from __future__ import annotations

import json
import re
import threading
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
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._state: dict[str, Any] = {"schemaVersion": 1, "devices": {}}
        self._load()

    def configure(self, path: Path) -> None:
        with self._lock:
            self.path = path.resolve()
            self._state = {"schemaVersion": 1, "devices": {}}
            self._load()

    def preference(self, serial: str) -> str | None:
        with self._lock:
            value = self._device(serial).get("preference")
            return value if isinstance(value, str) and value else None

    def set_preference(self, serial: str, encoder: str | None) -> None:
        with self._lock:
            device = self._device(serial)
            device["preference"] = validate_encoder_name(encoder) if encoder else None
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
            self._device(serial)["benchmarks"] = [result.to_dict() for result in results]
            self._save()

    def recommended(self, serial: str) -> str | None:
        preferred = self.preference(serial)
        if preferred:
            return preferred
        successful = [
            result
            for result in self.benchmark_results(serial)
            if result.success and result.startup_ms is not None
        ]
        if not successful:
            return None
        return min(successful, key=lambda item: item.startup_ms or float("inf")).encoder

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
            self._state = value

    def _save(self) -> None:
        if self.path is None:
            return
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
