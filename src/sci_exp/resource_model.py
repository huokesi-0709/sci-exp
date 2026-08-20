from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any, Iterable


def build_resource_profile(
    rows: Iterable[dict[str, Any]],
    *,
    require_energy: bool = True,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("status") == "ok":
            grouped[str(row["configuration"])].append(row)
    if not grouped:
        raise ValueError("no successful experiment rows")
    latency: dict[str, float] = {}
    memory: dict[str, float] = {}
    energy: dict[str, float] = {}
    details: dict[str, Any] = {}
    missing_energy = []
    for configuration, samples in sorted(grouped.items()):
        latencies = [float(row["latency_ms"]) for row in samples]
        memories = [
            float(row["telemetry"]["process_peak_rss_mb"])
            for row in samples
            if row.get("telemetry", {}).get("process_peak_rss_mb") is not None
        ]
        energies = [
            float(row["telemetry"]["energy_j"])
            for row in samples
            if row.get("telemetry", {}).get("energy_j") is not None
        ]
        latency[configuration] = statistics.median(latencies)
        if memories:
            memory[configuration] = statistics.median(memories)
        if energies:
            energy[configuration] = statistics.median(energies)
        else:
            missing_energy.append(configuration)
        details[configuration] = {
            "n_runs": len(samples),
            "latency_ms_median": latency[configuration],
            "latency_ms_p95": _percentile(latencies, 0.95),
            "memory_mb_median": memory.get(configuration),
            "energy_j_median": energy.get(configuration),
            "energy_samples": len(energies),
        }
    if require_energy and missing_energy:
        raise ValueError(
            "physical energy samples are missing for configurations "
            f"{missing_energy}; configure telemetry.power_paths or an external meter"
        )
    return {
        "schema_version": "1.0",
        "source": "measured_on_runtime_host",
        "predicted_latency_ms": latency,
        "predicted_memory_mb": memory,
        "predicted_energy_j": energy,
        "details": details,
    }


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction
