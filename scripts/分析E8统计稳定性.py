from __future__ import annotations

import argparse
import json
import math
import random
import statistics
from collections import defaultdict
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


def aggregate(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        telemetry = row.get("telemetry") or {}
        value = telemetry.get("energy_j")
        if row.get("status") != "ok" or value is None or telemetry.get("external_meter_valid") is False:
            continue
        grouped[str(row.get("query_id", ""))].append(row)
    return {
        query_id: {
            "energy_j": statistics.mean(float(row["telemetry"]["energy_j"]) for row in values),
            "safe": statistics.mean(float(is_safe(row)) for row in values),
            "latency_ms": statistics.mean(float(row["latency_ms"]) for row in values),
        }
        for query_id, values in grouped.items()
        if query_id
    }


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def describe(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "mean": statistics.mean(values) if values else None,
        "sd": statistics.stdev(values) if len(values) > 1 else None,
        "median": statistics.median(values) if values else None,
        "p95": percentile(values, 0.95),
    }


def paired_bootstrap(
    reference: dict[str, dict[str, float]],
    method: dict[str, dict[str, float]],
    *,
    iterations: int,
    seed: int,
) -> dict[str, Any]:
    keys = sorted(set(reference) & set(method))
    if not keys:
        return {"n_paired_queries": 0}
    rng = random.Random(seed)
    observed_energy = statistics.mean(method[key]["energy_j"] - reference[key]["energy_j"] for key in keys)
    observed_safety = statistics.mean(method[key]["safe"] - reference[key]["safe"] for key in keys)
    energy_samples = []
    safety_samples = []
    for _ in range(iterations):
        chosen = [rng.choice(keys) for _ in keys]
        energy_samples.append(statistics.mean(method[key]["energy_j"] - reference[key]["energy_j"] for key in chosen))
        safety_samples.append(statistics.mean(method[key]["safe"] - reference[key]["safe"] for key in chosen))
    return {
        "n_paired_queries": len(keys),
        "energy_difference_j_method_minus_reference": observed_energy,
        "energy_difference_95_ci": [percentile(energy_samples, 0.025), percentile(energy_samples, 0.975)],
        "safety_rate_difference_method_minus_reference": observed_safety,
        "safety_difference_95_ci": [percentile(safety_samples, 0.025), percentile(safety_samples, 0.975)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="E8 query-level配对bootstrap与稳定性统计")
    parser.add_argument("--method", action="append", required=True, help="NAME=RUNS.jsonl")
    parser.add_argument("--reference", required=True)
    parser.add_argument("--iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    methods = {}
    for spec in args.method:
        if "=" not in spec:
            raise SystemExit("--method格式必须为NAME=PATH")
        name, path = spec.split("=", 1)
        methods[name] = aggregate(read_rows(Path(path)))
    if args.reference not in methods:
        raise SystemExit(f"reference不存在: {args.reference}")
    report: dict[str, Any] = {
        "schema_version": "e8-statistical-stability-v1.0",
        "bootstrap_iterations": args.iterations,
        "seed": args.seed,
        "reference": args.reference,
        "descriptive": {},
        "paired_comparisons": {},
    }
    for name, values in methods.items():
        report["descriptive"][name] = {
            "energy_j": describe([row["energy_j"] for row in values.values()]),
            "latency_ms": describe([row["latency_ms"] for row in values.values()]),
            "safety_rate": statistics.mean(row["safe"] for row in values.values()) if values else None,
        }
        if name != args.reference:
            report["paired_comparisons"][name] = paired_bootstrap(
                methods[args.reference], values, iterations=args.iterations, seed=args.seed
            )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"reference": args.reference, "methods": list(methods), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
