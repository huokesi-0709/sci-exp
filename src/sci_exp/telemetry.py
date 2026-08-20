from __future__ import annotations

import os
import platform
import json
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # Windows
    resource = None  # type: ignore[assignment]


@dataclass
class TelemetrySample:
    monotonic_seconds: float
    temperature_c: float | None
    available_memory_mb: float | None
    load_1m: float | None
    power_w: float | None
    cpu_frequency_mhz: float | None
    cooling_state: float | None
    process_rss_mb: float | None


class TelemetrySampler:
    def __init__(
        self,
        *,
        interval_seconds: float = 0.1,
        power_paths: list[str] | None = None,
        power_scale: float = 0.000001,
        external_marker_host: str = "",
        external_marker_port: int = 8765,
    ) -> None:
        self.interval_seconds = max(interval_seconds, 0.01)
        self.power_paths = [Path(path) for path in (power_paths or [])]
        self.power_scale = power_scale
        self.external_marker_host = external_marker_host
        self.external_marker_port = external_marker_port
        self.external_markers_sent = 0
        self.external_marker_errors: list[str] = []
        self.external_marker_rtt_ms: list[float] = []
        self.samples: list[TelemetrySample] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("telemetry sampler already started")
        self._stop_event.clear()
        self.samples = [read_sample(self.power_paths, self.power_scale)]
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> dict[str, Any]:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.interval_seconds * 4))
        self.samples.append(read_sample(self.power_paths, self.power_scale))
        summary = summarize_samples(self.samples)
        summary["external_markers_sent"] = self.external_markers_sent
        summary["external_marker_errors"] = list(self.external_marker_errors)
        summary["external_marker_rtt_ms"] = list(self.external_marker_rtt_ms)
        return summary

    def mark(self, event: str, payload: dict[str, Any]) -> None:
        if not self.external_marker_host:
            return
        value = {
            "schema": "ina226-marker-v1.0",
            "event": event,
            "sender_epoch_ns": time.time_ns(),
            "sender_monotonic_ns": time.monotonic_ns(),
            **payload,
        }
        try:
            packet = json.dumps(value, ensure_ascii=False).encode("utf-8")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(0.25)
                started = time.perf_counter()
                client.sendto(
                    packet,
                    (self.external_marker_host, self.external_marker_port),
                )
                acknowledgement, _ = client.recvfrom(4096)
                ack_value = json.loads(acknowledgement.decode("utf-8"))
                if (
                    not isinstance(ack_value, dict)
                    or ack_value.get("type") != "marker_ack"
                    or ack_value.get("event") != event
                    or ack_value.get("run_key") != payload.get("run_key")
                ):
                    raise OSError("invalid external marker acknowledgement")
                self.external_marker_rtt_ms.append(
                    (time.perf_counter() - started) * 1000.0
                )
            self.external_markers_sent += 1
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.external_marker_errors.append(f"{type(exc).__name__}:{exc}")

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            self.samples.append(read_sample(self.power_paths, self.power_scale))


def read_sample(power_paths: list[Path], power_scale: float) -> TelemetrySample:
    return TelemetrySample(
        monotonic_seconds=time.perf_counter(),
        temperature_c=_read_temperature(),
        available_memory_mb=_read_available_memory(),
        load_1m=_read_load(),
        power_w=_read_power(power_paths, power_scale),
        cpu_frequency_mhz=_read_cpu_frequency_mhz(),
        cooling_state=_read_cooling_state(),
        process_rss_mb=_read_process_rss_mb(),
    )


def summarize_samples(samples: list[TelemetrySample]) -> dict[str, Any]:
    temperatures = [sample.temperature_c for sample in samples if sample.temperature_c is not None]
    memories = [
        sample.available_memory_mb
        for sample in samples
        if sample.available_memory_mb is not None
    ]
    loads = [sample.load_1m for sample in samples if sample.load_1m is not None]
    frequencies = [
        sample.cpu_frequency_mhz
        for sample in samples
        if sample.cpu_frequency_mhz is not None
    ]
    cooling_states = [
        sample.cooling_state
        for sample in samples
        if sample.cooling_state is not None
    ]
    process_rss = [
        sample.process_rss_mb
        for sample in samples
        if sample.process_rss_mb is not None
    ]
    power_samples = [sample for sample in samples if sample.power_w is not None]
    energy_j: float | None = None
    if len(power_samples) >= 2:
        energy_j = sum(
            (right.monotonic_seconds - left.monotonic_seconds)
            * ((left.power_w or 0.0) + (right.power_w or 0.0))
            / 2.0
            for left, right in zip(power_samples, power_samples[1:])
        )
    duration_seconds = (
        samples[-1].monotonic_seconds - samples[0].monotonic_seconds
        if len(samples) >= 2
        else 0.0
    )
    return {
        "telemetry_schema_version": "2.0",
        "sample_count": len(samples),
        "duration_seconds": duration_seconds,
        "effective_sample_rate_hz": (
            (len(samples) - 1) / duration_seconds
            if len(samples) >= 2 and duration_seconds > 0
            else None
        ),
        # Legacy names are retained for existing analysis scripts.
        "temperature_c_start": temperatures[0] if temperatures else None,
        "temperature_c_peak": max(temperatures) if temperatures else None,
        "device_temperature_c_start": temperatures[0] if temperatures else None,
        "device_temperature_c_end": temperatures[-1] if temperatures else None,
        "device_temperature_c_peak": max(temperatures) if temperatures else None,
        "available_memory_mb_min": min(memories) if memories else None,
        "load_1m_peak": max(loads) if loads else None,
        "cpu_frequency_mhz_start": frequencies[0] if frequencies else None,
        "cpu_frequency_mhz_min": min(frequencies) if frequencies else None,
        "cpu_frequency_mhz_max": max(frequencies) if frequencies else None,
        "cooling_state_peak": max(cooling_states) if cooling_states else None,
        "thermal_throttling_observed": (
            any(value > 0 for value in cooling_states)
            if cooling_states
            else None
        ),
        "energy_j": energy_j,
        "energy_measurement": (
            "physical_power_path_integral" if energy_j is not None else "unavailable"
        ),
        "process_peak_rss_mb": (
            max(process_rss) if process_rss else _process_peak_rss_mb()
        ),
    }


def device_info() -> dict[str, Any]:
    thermal_zones = _thermal_zone_info()
    cooling_devices = _cooling_device_info()
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "temperature_c": _read_temperature(),
        "device_temperature_c": _read_temperature(),
        "cpu_frequency_mhz": _read_cpu_frequency_mhz(),
        "cooling_state": _read_cooling_state(),
        "available_memory_mb": _read_available_memory(),
        "load_1m": _read_load(),
        "thermal_zones": thermal_zones,
        "cooling_devices": cooling_devices,
        "thermal_paths": [item["temp_path"] for item in thermal_zones],
    }


def _read_temperature() -> float | None:
    values = []
    for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        value = _read_number(path)
        if value is not None:
            values.append(value / 1000.0 if value > 200 else value)
    return max(values) if values else None


def _thermal_zone_info() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for directory in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        temperature = _read_number(directory / "temp")
        if temperature is not None and temperature > 200:
            temperature /= 1000.0
        result.append(
            {
                "name": directory.name,
                "type": _read_text(directory / "type"),
                "temperature_c": temperature,
                "temp_path": str(directory / "temp"),
            }
        )
    return result


def _cooling_device_info() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for directory in sorted(Path("/sys/class/thermal").glob("cooling_device*")):
        result.append(
            {
                "name": directory.name,
                "type": _read_text(directory / "type"),
                "cur_state": _read_number(directory / "cur_state"),
                "max_state": _read_number(directory / "max_state"),
            }
        )
    return result


def _read_cpu_frequency_mhz() -> float | None:
    values = [
        value
        for path in Path("/sys/devices/system/cpu").glob(
            "cpu[0-9]*/cpufreq/scaling_cur_freq"
        )
        if (value := _read_number(path)) is not None
    ]
    return max(values) / 1000.0 if values else None


def _read_cooling_state() -> float | None:
    values = [
        value
        for path in Path("/sys/class/thermal").glob("cooling_device*/cur_state")
        if (value := _read_number(path)) is not None
    ]
    return max(values) if values else None


def _read_available_memory() -> float | None:
    path = Path("/proc/meminfo")
    if not path.exists():
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return float(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        return None
    return None


def _read_load() -> float | None:
    try:
        return float(os.getloadavg()[0])
    except (AttributeError, OSError):
        return None


def _read_power(paths: list[Path], scale: float) -> float | None:
    values = [_read_number(path) for path in paths]
    usable = [value for value in values if value is not None]
    return sum(usable) * scale if usable else None


def _read_number(path: Path) -> float | None:
    try:
        return float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _read_process_rss_mb() -> float | None:
    path = Path("/proc/self/status")
    if not path.exists():
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        return None
    return None


def _process_peak_rss_mb() -> float | None:
    if resource is None:
        return None
    try:
        value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return value / 1024.0 if platform.system() != "Darwin" else value / (1024.0 * 1024.0)
    except (AttributeError, ValueError):
        return None
