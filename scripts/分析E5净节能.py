from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def energies(path: Path) -> list[float]:
    values = []
    for row in read_rows(path):
        telemetry = row.get("telemetry") or {}
        value = telemetry.get("energy_j")
        if row.get("status", "ok") == "ok" and value is not None and telemetry.get("external_meter_valid") is not False:
            values.append(float(value))
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="E5 gross saving / router cost / net saving")
    parser.add_argument("--baseline-runs", required=True, type=Path)
    parser.add_argument("--method-runs", required=True, type=Path)
    parser.add_argument("--router-energy", required=True, type=Path, help="E5_router_batch经INA226整合后的JSONL")
    parser.add_argument("--router-calls", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    baseline = energies(args.baseline_runs)
    method = energies(args.method_runs)
    router_rows = read_rows(args.router_energy)
    router_batch = [float(row["energy_j"]) for row in router_rows if row.get("valid") and row.get("energy_j") is not None]
    if not baseline or not method or not router_batch or args.router_calls <= 0:
        raise SystemExit("缺少有效基线、方法或router batch物理能耗")
    baseline_mean = statistics.mean(baseline)
    method_e2e = statistics.mean(method)
    router_cost = statistics.mean(router_batch) / args.router_calls
    generation_without_router = max(0.0, method_e2e - router_cost)
    gross = baseline_mean - generation_without_router
    net = baseline_mean - method_e2e
    report = {
        "schema_version": "e5-net-energy-v1.0",
        "baseline_energy_j_mean": baseline_mean,
        "method_e2e_energy_j_mean": method_e2e,
        "router_energy_j_per_query": router_cost,
        "gross_saving_j": gross,
        "net_saving_j": net,
        "router_cost_as_fraction_of_gross_saving": router_cost / gross if gross > 0 else None,
        "net_saving_fraction_vs_baseline": net / baseline_mean if baseline_mean > 0 else None,
        "accounting_identity": "net = baseline - method_E2E; method_E2E已包含router，不能再次扣除router成本",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
