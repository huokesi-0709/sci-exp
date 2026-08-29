from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按query_start/query_end积分INA226功率并汇总SHT31环境数据"
    )
    parser.add_argument("--meter-log", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--maximum-gap-ms", type=float, default=30.0)
    parser.add_argument(
        "--idle-power-w",
        type=float,
        help="显式空闲功率；省略时从idle_start/idle_end标记区间自动估计",
    )
    parser.add_argument("--runs", type=Path)
    parser.add_argument("--merged-runs-output", type=Path)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}不是对象")
            rows.append(value)
    return rows


def sample_timing(samples: list[dict[str, Any]]) -> tuple[str, float]:
    """Return the authoritative timing field and its units per second.

    Markers are received by the Windows collector, so their boundaries must
    remain on ``host_monotonic_ns``.  Once samples inside that boundary have
    been selected, however, INA226 integration and continuity validation must
    use the ESP32 device clock when it is present.  Host receive timestamps are
    affected by Windows scheduler quanta and are only an arrival-path audit
    signal, not a power-sampling clock.
    """
    if samples and all(row.get("device_us") is not None for row in samples):
        return "device_us", 1_000_000.0
    return "host_monotonic_ns", 1_000_000_000.0


def maximum_host_arrival_gap_ms(samples: list[dict[str, Any]]) -> float:
    if len(samples) < 2:
        return float("inf")
    return max(
        (int(right["host_monotonic_ns"]) - int(left["host_monotonic_ns"]))
        / 1_000_000.0
        for left, right in zip(samples, samples[1:])
    )


def integrate(samples: list[dict[str, Any]]) -> tuple[float | None, float]:
    if len(samples) < 2:
        return None, float("inf")
    timing_field, units_per_second = sample_timing(samples)
    energy = 0.0
    maximum_gap_ms = 0.0
    for left, right in zip(samples, samples[1:]):
        delta_s = (
            int(right[timing_field]) - int(left[timing_field])
        ) / units_per_second
        maximum_gap_ms = max(maximum_gap_ms, delta_s * 1000.0)
        energy += (
            delta_s
            * (float(left["power_w"]) + float(right["power_w"]))
            / 2.0
        )
    return energy, maximum_gap_ms


def estimate_idle_power(
    samples: list[dict[str, Any]], markers: list[dict[str, Any]]
) -> tuple[float | None, dict[str, Any]]:
    intervals: dict[str, dict[str, dict[str, Any]]] = {}
    for marker in markers:
        event = str(marker.get("event", ""))
        run_key = str(marker.get("run_key", ""))
        if event in {"idle_start", "idle_end"} and run_key:
            intervals.setdefault(run_key, {})[event] = marker
    estimates: list[float] = []
    details: list[dict[str, Any]] = []
    for run_key, pair in sorted(intervals.items()):
        if "idle_start" not in pair or "idle_end" not in pair:
            continue
        start_ns = int(pair["idle_start"]["host_monotonic_ns"])
        end_ns = int(pair["idle_end"]["host_monotonic_ns"])
        selected = [
            row
            for row in samples
            if start_ns <= int(row["host_monotonic_ns"]) <= end_ns
        ]
        energy_j, maximum_gap_ms = integrate(selected)
        duration_s = (end_ns - start_ns) / 1_000_000_000.0
        if energy_j is None or duration_s <= 0:
            continue
        mean_power_w = energy_j / duration_s
        estimates.append(mean_power_w)
        details.append(
            {
                "run_key": run_key,
                "sample_count": len(selected),
                "duration_s": duration_s,
                "maximum_sample_gap_ms": maximum_gap_ms,
                "integration_timing_source": sample_timing(selected)[0]
                if selected
                else None,
                "maximum_host_arrival_gap_ms": maximum_host_arrival_gap_ms(selected),
                "mean_power_w": mean_power_w,
            }
        )
    return (
        sum(estimates) / len(estimates) if estimates else None,
        {"intervals": details, "interval_count": len(details)},
    )


def summarize_environment(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [
        row
        for row in rows
        if row.get("valid") is True
        and row.get("ambient_temperature_c") is not None
        and row.get("ambient_relative_humidity_pct") is not None
    ]
    temperatures = [float(row["ambient_temperature_c"]) for row in valid]
    humidities = [float(row["ambient_relative_humidity_pct"]) for row in valid]
    return {
        "environment_sample_count": len(valid),
        "ambient_temperature_c_start": temperatures[0] if temperatures else None,
        "ambient_temperature_c_end": temperatures[-1] if temperatures else None,
        "ambient_temperature_c_mean": (
            sum(temperatures) / len(temperatures) if temperatures else None
        ),
        "ambient_temperature_c_peak": max(temperatures) if temperatures else None,
        "ambient_relative_humidity_pct_start": humidities[0] if humidities else None,
        "ambient_relative_humidity_pct_end": humidities[-1] if humidities else None,
        "ambient_relative_humidity_pct_mean": (
            sum(humidities) / len(humidities) if humidities else None
        ),
    }


def select_environment_rows(
    rows: list[dict[str, Any]], start_ns: int, end_ns: int
) -> list[dict[str, Any]]:
    timed = [
        row
        for row in rows
        if row.get("type") == "environment"
        and row.get("host_monotonic_ns") is not None
    ]
    inside = [
        row
        for row in timed
        if start_ns <= int(row["host_monotonic_ns"]) <= end_ns
    ]
    before = [row for row in timed if int(row["host_monotonic_ns"]) < start_ns]
    after = [row for row in timed if int(row["host_monotonic_ns"]) > end_ns]
    selected = list(inside)
    if before:
        selected.insert(0, max(before, key=lambda row: int(row["host_monotonic_ns"])))
    if after:
        selected.append(min(after, key=lambda row: int(row["host_monotonic_ns"])))
    unique: dict[int, dict[str, Any]] = {
        int(row["host_monotonic_ns"]): row for row in selected
    }
    return [unique[key] for key in sorted(unique)]


def merge_energy_into_runs(
    run_rows: list[dict[str, Any]], energy_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_key = {str(row.get("run_key", "")): row for row in energy_rows}
    merged: list[dict[str, Any]] = []
    for original in run_rows:
        row = dict(original)
        run_key = str(row.get("run_key", ""))
        measurement = by_key.get(run_key)
        telemetry = dict(row.get("telemetry") or {})
        if measurement is None:
            telemetry.update(
                {
                    "energy_j": None,
                    "energy_measurement": "external_meter_missing_run_key",
                    "external_meter_valid": False,
                }
            )
        else:
            telemetry.update(
                {
                    "energy_j": measurement.get("energy_j")
                    if measurement.get("valid")
                    else None,
                    "energy_measurement": "external_ina226_r010_high_side",
                    "external_meter_valid": bool(measurement.get("valid")),
                    "external_meter_quality": {
                        "sample_count": measurement.get("sample_count"),
                        "maximum_sample_gap_ms": measurement.get(
                            "maximum_sample_gap_ms"
                        ),
                        "flags": measurement.get("flags", {}),
                        "reason": measurement.get("reason"),
                    },
                }
            )
            for key, value in measurement.items():
                if key.startswith("ambient_") or key == "environment_sample_count":
                    telemetry[key] = value
        row["telemetry"] = telemetry
        merged.append(row)
    return merged


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    rows = read_rows(args.meter_log)
    samples = [
        row
        for row in rows
        if row.get("type") == "sample"
        and row.get("host_monotonic_ns") is not None
        and row.get("power_w") is not None
    ]
    markers = [row for row in rows if row.get("type") == "marker"]
    environment_rows = [row for row in rows if row.get("type") == "environment"]
    estimated_idle_power_w, idle_details = estimate_idle_power(samples, markers)
    idle_power_w = (
        float(args.idle_power_w)
        if args.idle_power_w is not None
        else estimated_idle_power_w
    )
    boundaries: dict[str, dict[str, dict[str, Any]]] = {}
    for marker in markers:
        run_key = str(marker.get("run_key", ""))
        event = str(marker.get("event", ""))
        if run_key and event in {"query_start", "query_end"}:
            boundaries.setdefault(run_key, {})[event] = marker

    results = []
    for run_key, pair in sorted(boundaries.items()):
        start = pair.get("query_start")
        end = pair.get("query_end")
        if not start or not end:
            results.append(
                {
                    "run_key": run_key,
                    "valid": False,
                    "reason": "missing_start_or_end_marker",
                }
            )
            continue
        start_ns = int(start["host_monotonic_ns"])
        end_ns = int(end["host_monotonic_ns"])
        selected = [
            sample
            for sample in samples
            if start_ns <= int(sample["host_monotonic_ns"]) <= end_ns
        ]
        gross_energy_j, maximum_gap_ms = integrate(selected)
        duration_s = (end_ns - start_ns) / 1_000_000_000.0
        net_energy_j = (
            gross_energy_j - idle_power_w * duration_s
            if gross_energy_j is not None and idle_power_w is not None
            else None
        )
        environment = summarize_environment(
            select_environment_rows(environment_rows, start_ns, end_ns)
        )
        flags = {
            "undervoltage": any(bool(row.get("undervoltage")) for row in selected),
            "current_saturated": any(
                bool(row.get("current_saturated")) for row in selected
            ),
            "shunt_near_limit": any(
                bool(row.get("shunt_near_limit")) for row in selected
            ),
            "integration_gap": any(
                bool(row.get("integration_gap")) for row in selected
            ),
        }
        valid = (
            gross_energy_j is not None
            and net_energy_j is not None
            and net_energy_j >= 0
            and maximum_gap_ms <= args.maximum_gap_ms
            and not any(flags.values())
            and end_ns > start_ns
        )
        results.append(
            {
                "schema_version": "ina226-query-energy-v2.0",
                "run_key": run_key,
                "query_id": start.get("query_id", ""),
                "configuration": start.get("configuration", ""),
                "repetition": start.get("repetition", 0),
                "sample_count": len(selected),
                "duration_ms": (end_ns - start_ns) / 1_000_000.0,
                "energy_gross_j": gross_energy_j,
                "idle_power_w": idle_power_w,
                "energy_net_j": net_energy_j,
                "energy_j": net_energy_j,
                "mean_power_w": (
                    gross_energy_j / duration_s
                    if gross_energy_j is not None and duration_s > 0
                    else None
                ),
                "maximum_sample_gap_ms": maximum_gap_ms,
                "integration_timing_source": sample_timing(selected)[0]
                if selected
                else None,
                "maximum_host_arrival_gap_ms": maximum_host_arrival_gap_ms(selected),
                "flags": flags,
                "valid": valid,
                "reason": (
                    "ok"
                    if valid
                    else "missing_idle_power_baseline"
                    if idle_power_w is None
                    else "negative_net_energy"
                    if net_energy_j is not None and net_energy_j < 0
                    else "quality_gate_failed"
                ),
                **environment,
            }
        )
    write_rows(args.output, results)
    if bool(args.runs) != bool(args.merged_runs_output):
        raise SystemExit("--runs与--merged-runs-output必须同时提供")
    merged_count = 0
    if args.runs and args.merged_runs_output:
        merged = merge_energy_into_runs(read_rows(args.runs), results)
        write_rows(args.merged_runs_output, merged)
        merged_count = len(merged)
    summary = {
        "output": str(args.output),
        "run_count": len(results),
        "valid_count": sum(bool(row.get("valid")) for row in results),
        "invalid_count": sum(not bool(row.get("valid")) for row in results),
        "idle_power_w": idle_power_w,
        "idle_baseline": idle_details,
        "merged_runs_output": (
            str(args.merged_runs_output) if args.merged_runs_output else None
        ),
        "merged_run_count": merged_count,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if results and summary["invalid_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
