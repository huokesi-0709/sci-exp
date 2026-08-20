from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def relative_error(measured: float, reference: float) -> float:
    if reference == 0:
        raise ValueError("reference value cannot be zero")
    return abs(measured - reference) / abs(reference)


def main() -> int:
    parser = argparse.ArgumentParser(description="验证INA226三点电压/电流/功率校准")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--maximum-relative-error", type=float, default=0.02)
    args = parser.parse_args()
    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 3:
        raise ValueError("至少需要三个校准点")
    results = []
    instrument_ids = set()
    for row in rows:
        required = (
            "reference_voltage_v",
            "reference_current_a",
            "measured_bus_v",
            "measured_current_a",
            "duration_s",
            "environment_temperature_c",
            "reference_instrument_id",
        )
        missing = [field for field in required if not str(row.get(field, "")).strip()]
        if missing:
            raise ValueError(f"{row.get('point_id')}:缺少{','.join(missing)}")
        reference_v = float(row["reference_voltage_v"])
        reference_a = float(row["reference_current_a"])
        measured_v = float(row["measured_bus_v"])
        measured_a = float(row["measured_current_a"])
        reference_w = reference_v * reference_a
        measured_w = measured_v * measured_a
        errors = {
            "voltage": relative_error(measured_v, reference_v),
            "current": relative_error(measured_a, reference_a),
            "power": relative_error(measured_w, reference_w),
        }
        instrument_ids.add(row["reference_instrument_id"].strip())
        results.append(
            {
                "point_id": row.get("point_id", ""),
                "reference_voltage_v": reference_v,
                "reference_current_a": reference_a,
                "reference_power_w": reference_w,
                "measured_bus_v": measured_v,
                "measured_current_a": measured_a,
                "measured_power_w": measured_w,
                "duration_s": float(row["duration_s"]),
                "environment_temperature_c": float(
                    row["environment_temperature_c"]
                ),
                "relative_errors": errors,
                "pass": all(
                    value <= args.maximum_relative_error
                    for value in errors.values()
                ),
            }
        )
    currents = sorted(item["reference_current_a"] for item in results)
    coverage_gate = currents[0] <= 0.6 and currents[-1] >= 1.8
    gates = {
        "at_least_three_points": len(results) >= 3,
        "covers_low_and_high_current": coverage_gate,
        "single_identified_reference_instrument": (
            len(instrument_ids) == 1 and "" not in instrument_ids
        ),
        "all_points_within_error_limit": all(item["pass"] for item in results),
        "all_points_at_least_30_seconds": all(
            item["duration_s"] >= 30 for item in results
        ),
    }
    report = {
        "schema_version": "ina226-three-point-calibration-v1.0",
        "input": str(args.input),
        "maximum_relative_error": args.maximum_relative_error,
        "reference_instrument_ids": sorted(instrument_ids),
        "points": results,
        "gates": gates,
        "calibration_pass": all(gates.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["calibration_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

