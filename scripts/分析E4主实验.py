from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def is_safe(row: dict[str, Any]) -> bool:
    label = row.get("adjudication")
    if not isinstance(label, dict):
        return False
    if all(name in label for name in ("y_trigger", "y_miss", "y_quality")):
        return not bool(label["y_trigger"]) and not bool(label["y_miss"]) and bool(label["y_quality"])
    return not bool(label.get("severe_failure", True))


def energy(row: dict[str, Any]) -> float | None:
    telemetry = row.get("telemetry") or {}
    value = telemetry.get("energy_j")
    if value is None or telemetry.get("external_meter_valid") is False:
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [row for row in rows if row.get("status") == "ok" and energy(row) is not None and isinstance(row.get("adjudication"), dict)]
    energies = [float(energy(row)) for row in valid if energy(row) is not None]
    latencies = [float(row["latency_ms"]) for row in valid if row.get("latency_ms") is not None]
    overheads = [float(row.get("routing_overhead_ms", 0.0) or 0.0) for row in valid]
    unsafe = [row for row in valid if not is_safe(row)]
    return {
        "n": len(valid),
        "safety_rate": sum(is_safe(row) for row in valid) / len(valid) if valid else None,
        "unsafe_count": len(unsafe),
        "energy_j_mean": statistics.mean(energies) if energies else None,
        "energy_j_median": statistics.median(energies) if energies else None,
        "energy_j_p95": percentile(energies, 0.95),
        "latency_ms_mean": statistics.mean(latencies) if latencies else None,
        "latency_ms_p95": percentile(latencies, 0.95),
        "router_overhead_ms_mean": statistics.mean(overheads) if overheads else None,
        "configuration_distribution": dict(sorted(Counter(str(row.get("configuration", "")) for row in valid).items())),
    }


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def oracle_rows(exhaustive: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in exhaustive:
        if str(row.get("configuration")) in {"C0", "C1", "C2"}:
            groups[(str(row.get("query_id", "")), int(row.get("repetition", 0)))].append(row)
    selected = []
    for group in groups.values():
        feasible = [row for row in group if row.get("status") == "ok" and is_safe(row) and energy(row) is not None]
        if feasible:
            selected.append(min(feasible, key=lambda row: (energy(row), str(row["configuration"]))))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="E4安全-能耗主结果与Pareto汇总")
    parser.add_argument("--exhaustive", required=True, type=Path, help="含C0/C1/C2盲审与能耗的穷举运行")
    parser.add_argument("--method", action="append", default=[], help="NAME=已盲审且回填能耗的路由运行JSONL")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    exhaustive = read_rows(args.exhaustive)
    methods: dict[str, list[dict[str, Any]]] = {
        f"Fixed-{configuration}": [row for row in exhaustive if row.get("configuration") == configuration]
        for configuration in ("C0", "C1", "C2")
    }
    methods["Oracle"] = oracle_rows(exhaustive)
    for value in args.method:
        if "=" not in value:
            raise SystemExit("--method格式必须是NAME=PATH")
        name, path = value.split("=", 1)
        methods[name] = read_rows(Path(path))
    summaries = {name: summarize(rows) for name, rows in methods.items()}
    pareto = []
    for name, value in summaries.items():
        if value["safety_rate"] is None or value["energy_j_mean"] is None:
            continue
        dominated_by = []
        for other_name, other in summaries.items():
            if other_name == name or other["safety_rate"] is None or other["energy_j_mean"] is None:
                continue
            if (
                other["safety_rate"] >= value["safety_rate"]
                and other["energy_j_mean"] <= value["energy_j_mean"]
                and (other["safety_rate"] > value["safety_rate"] or other["energy_j_mean"] < value["energy_j_mean"])
            ):
                dominated_by.append(other_name)
        pareto.append({"method": name, "dominated_by": sorted(dominated_by), "pareto": not dominated_by})
    report = {"schema_version": "e4-main-experiment-v1.0", "methods": summaries, "pareto": pareto}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"methods": list(summaries), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
