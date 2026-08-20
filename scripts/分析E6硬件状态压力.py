from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row.get("status") == "ok" and isinstance(row.get("routing"), dict)]
    temperatures = []
    memories = []
    frequencies = []
    energy_violations = 0
    budgeted = 0
    c3 = 0
    for row in valid:
        routing = row["routing"]
        state = routing.get("state_at_decision") or {}
        if state.get("device_temperature_c_start") is not None:
            temperatures.append(float(state["device_temperature_c_start"]))
        if state.get("available_memory_mb_min") is not None:
            memories.append(float(state["available_memory_mb_min"]))
        if state.get("cpu_frequency_mhz_start") is not None:
            frequencies.append(float(state["cpu_frequency_mhz_start"]))
        if str(row.get("configuration")) == "C3":
            c3 += 1
        budget = routing.get("energy_budget_j")
        energy = (row.get("telemetry") or {}).get("energy_j")
        if budget is not None and energy is not None:
            budgeted += 1
            energy_violations += float(energy) > float(budget)
    return {
        "n": len(valid),
        "configuration_distribution": dict(sorted(Counter(str(row.get("configuration", "")) for row in valid).items())),
        "fallback_rate": c3 / len(valid) if valid else None,
        "temperature_c_mean": statistics.mean(temperatures) if temperatures else None,
        "temperature_c_range": [min(temperatures), max(temperatures)] if temperatures else None,
        "available_memory_mb_mean": statistics.mean(memories) if memories else None,
        "cpu_frequency_mhz_mean": statistics.mean(frequencies) if frequencies else None,
        "energy_budget_violation_rate": energy_violations / budgeted if budgeted else None,
        "budgeted_runs": budgeted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="E6温度/内存headroom/available energy budget状态压力分析")
    parser.add_argument("--scenario", action="append", required=True, help="NAME=ROUTED_RUNS.jsonl")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    scenarios = {}
    for spec in args.scenario:
        if "=" not in spec:
            raise SystemExit("--scenario格式必须为NAME=PATH")
        name, path = spec.split("=", 1)
        scenarios[name] = summarize(read_rows(Path(path)))
    report = {
        "schema_version": "e6-hardware-state-stress-v1.0",
        "scenarios": scenarios,
        "temperature_rule": "先用SoC温度、CPU频率和cooling state探索热行为，再冻结low/near-limit/throttled；SHT31仅为ambient reference。",
        "memory_rule": "使用低CPU内存占用改变available memory headroom；不得用高CPU stress-ng冒充纯内存实验。",
        "energy_rule": "变量是available energy budget，不是battery state-of-charge。",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scenarios": list(scenarios), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
