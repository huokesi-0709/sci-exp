from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{number}不是JSON对象")
            rows.append(value)
    return rows


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def sample_quality(samples: list[dict[str, Any]], expected_hz: float) -> dict[str, Any]:
    ordered = sorted(samples, key=lambda row: int(row["host_monotonic_ns"]))
    gaps_ms = [
        (int(right["host_monotonic_ns"]) - int(left["host_monotonic_ns"]))
        / 1_000_000.0
        for left, right in zip(ordered, ordered[1:])
    ]
    duration_s = (
        (int(ordered[-1]["host_monotonic_ns"]) - int(ordered[0]["host_monotonic_ns"]))
        / 1_000_000_000.0
        if len(ordered) >= 2
        else 0.0
    )
    effective_hz = (len(ordered) - 1) / duration_s if duration_s > 0 else None
    expected_count = duration_s * expected_hz + 1.0
    dropout_fraction = (
        max(0.0, expected_count - len(ordered)) / expected_count
        if expected_count > 0
        else None
    )
    sequence_gaps = 0
    sequence_regressions = 0
    for left, right in zip(ordered, ordered[1:]):
        if left.get("seq") is None or right.get("seq") is None:
            continue
        delta = int(right["seq"]) - int(left["seq"])
        if delta < 1:
            sequence_regressions += 1
        elif delta > 1:
            sequence_gaps += delta - 1
    flags = {
        name: sum(bool(row.get(name)) for row in ordered)
        for name in (
            "current_saturated",
            "shunt_near_limit",
            "undervoltage",
            "integration_gap",
        )
    }
    return {
        "sample_count": len(ordered),
        "duration_s": duration_s,
        "effective_sample_rate_hz": effective_hz,
        "dropout_fraction": dropout_fraction,
        "gap_ms_p50": percentile(gaps_ms, 0.50),
        "gap_ms_p95": percentile(gaps_ms, 0.95),
        "gap_ms_p99": percentile(gaps_ms, 0.99),
        "gap_ms_max": max(gaps_ms) if gaps_ms else None,
        "sequence_missing_samples": sequence_gaps,
        "sequence_regressions": sequence_regressions,
        "quality_flag_counts": flags,
    }


def idle_quality(
    samples: list[dict[str, Any]], markers: list[dict[str, Any]]
) -> dict[str, Any]:
    pairs: dict[str, dict[str, dict[str, Any]]] = {}
    for marker in markers:
        event = str(marker.get("event", ""))
        key = str(marker.get("run_key", ""))
        if key and event in {"idle_start", "idle_end"}:
            pairs.setdefault(key, {})[event] = marker
    intervals = []
    for key, pair in sorted(pairs.items()):
        if set(pair) != {"idle_start", "idle_end"}:
            continue
        start = int(pair["idle_start"]["host_monotonic_ns"])
        end = int(pair["idle_end"]["host_monotonic_ns"])
        powers = [
            float(row["power_w"])
            for row in samples
            if start <= int(row["host_monotonic_ns"]) <= end
        ]
        if len(powers) < 2:
            continue
        intervals.append(
            {
                "run_key": key,
                "sample_count": len(powers),
                "duration_s": (end - start) / 1_000_000_000.0,
                "mean_power_w": statistics.mean(powers),
                "sd_power_w": statistics.stdev(powers),
            }
        )
    means = [float(item["mean_power_w"]) for item in intervals]
    all_idle_powers = []
    for item in intervals:
        key = str(item["run_key"])
        pair = pairs[key]
        start = int(pair["idle_start"]["host_monotonic_ns"])
        end = int(pair["idle_end"]["host_monotonic_ns"])
        all_idle_powers.extend(
            float(row["power_w"])
            for row in samples
            if start <= int(row["host_monotonic_ns"]) <= end
        )
    return {
        "intervals": intervals,
        "interval_count": len(intervals),
        "idle_power_w_mean": statistics.mean(all_idle_powers) if all_idle_powers else None,
        "idle_power_w_sd": statistics.stdev(all_idle_powers) if len(all_idle_powers) > 1 else None,
        "between_interval_sd_w": statistics.stdev(means) if len(means) > 1 else None,
    }


def sync_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rtts = []
    for row in rows:
        if row.get("type") != "sync_ack":
            continue
        request = row.get("sync_request_epoch_ns")
        received = row.get("host_epoch_ns")
        if request is None or received is None:
            continue
        value = (int(received) - int(request)) / 1_000_000.0
        if math.isfinite(value) and value >= 0:
            rtts.append(value)
    return {
        "sync_count": len(rtts),
        "rtt_ms_p50": percentile(rtts, 0.50),
        "rtt_ms_p95": percentile(rtts, 0.95),
        "rtt_ms_p99": percentile(rtts, 0.99),
        "rtt_ms_max": max(rtts) if rtts else None,
        "note": "旧采集日志若缺sync_request_epoch_ns，无法回算同步RTT",
    }


def marker_rtt_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = []
    for row in rows:
        telemetry = row.get("telemetry")
        if not isinstance(telemetry, dict):
            continue
        raw = telemetry.get("external_marker_rtt_ms", [])
        if isinstance(raw, list):
            values.extend(float(item) for item in raw if float(item) >= 0)
    return {
        "marker_rtt_count": len(values),
        "marker_rtt_ms_p50": percentile(values, 0.50),
        "marker_rtt_ms_p95": percentile(values, 0.95),
        "marker_rtt_ms_p99": percentile(values, 0.99),
        "marker_rtt_ms_max": max(values) if values else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="E0 INA226测量链质量审计")
    parser.add_argument("--meter-log", required=True, type=Path)
    parser.add_argument("--calibration-report", type=Path)
    parser.add_argument("--run-log", type=Path, help="含external_marker_rtt_ms的Radxa运行JSONL")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-hz", type=float, default=100.0)
    parser.add_argument("--minimum-hz", type=float, default=99.0)
    parser.add_argument("--maximum-gap-ms", type=float, default=30.0)
    parser.add_argument("--maximum-dropout-fraction", type=float, default=0.001)
    args = parser.parse_args()

    rows = read_jsonl(args.meter_log)
    samples = [
        row
        for row in rows
        if row.get("type") == "sample"
        and row.get("host_monotonic_ns") is not None
        and row.get("power_w") is not None
    ]
    markers = [row for row in rows if row.get("type") == "marker"]
    quality = sample_quality(samples, args.expected_hz)
    idle = idle_quality(samples, markers)
    sync = sync_quality(rows)
    marker_rtt = marker_rtt_quality(read_jsonl(args.run_log)) if args.run_log else marker_rtt_quality([])
    calibration = None
    if args.calibration_report:
        calibration = json.loads(args.calibration_report.read_text(encoding="utf-8"))
    gates = {
        "calibration_pass": bool(calibration and calibration.get("calibration_pass")),
        "effective_rate_pass": bool(
            quality["effective_sample_rate_hz"] is not None
            and quality["effective_sample_rate_hz"] >= args.minimum_hz
        ),
        "maximum_gap_pass": bool(
            quality["gap_ms_max"] is not None
            and quality["gap_ms_max"] <= args.maximum_gap_ms
        ),
        "dropout_pass": bool(
            quality["dropout_fraction"] is not None
            and quality["dropout_fraction"] <= args.maximum_dropout_fraction
        ),
        "sequence_pass": quality["sequence_regressions"] == 0,
        "quality_flags_pass": not any(quality["quality_flag_counts"].values()),
        "idle_baseline_present": idle["interval_count"] >= 3,
        "sync_samples_present": sync["sync_count"] >= 10,
        "marker_rtt_samples_present": marker_rtt["marker_rtt_count"] >= 100,
    }
    report = {
        "schema_version": "e0-power-chain-v1.0",
        "meter_log": str(args.meter_log),
        "calibration_report": str(args.calibration_report) if args.calibration_report else None,
        "sample_quality": quality,
        "idle": idle,
        "synchronization": sync,
        "query_marker_rtt": marker_rtt,
        "calibration": calibration,
        "gates": gates,
        "e0_pass": all(gates.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"gates": gates, "e0_pass": report["e0_pass"]}, ensure_ascii=False))
    return 0 if report["e0_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
