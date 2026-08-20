from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sci_exp.config import load_config  # noqa: E402
from sci_exp.runner import _build_router, _routing_state  # noqa: E402
from sci_exp.schemas import QueryRecord  # noqa: E402
from sci_exp.telemetry import TelemetrySampler  # noqa: E402


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def main() -> int:
    parser = argparse.ArgumentParser(description="E5 Router纯选择开销microbenchmark")
    parser.add_argument("--config", required=True)
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-key", default="E5_router_batch")
    args = parser.parse_args()
    config = load_config(args.config)
    router = _build_router(config)
    queries = [QueryRecord.from_dict(json.loads(line)) for line in args.queries.read_text(encoding="utf-8").splitlines() if line.strip()]
    state = _routing_state()
    durations = []
    decisions = {}
    sampler = TelemetrySampler(
        interval_seconds=0.2,
        external_marker_host=os.environ.get("SCI_EXP_METER_HOST", ""),
        external_marker_port=8765,
    )
    marker = {
        "run_key": args.run_key,
        "query_id": "E5_router_microbenchmark",
        "configuration": "ROUTER_ONLY",
        "repetition": 0,
    }
    sampler.start()
    sampler.mark("query_start", marker)
    for _ in range(args.iterations):
        for query in queries:
            started = time.perf_counter_ns()
            decision = router.select(query, state)
            durations.append((time.perf_counter_ns() - started) / 1_000_000.0)
            decisions[decision.configuration] = decisions.get(decision.configuration, 0) + 1
    sampler.mark("query_end", marker)
    telemetry = sampler.stop()
    report = {
        "schema_version": "e5-router-overhead-v1.0",
        "calls": len(durations),
        "iterations": args.iterations,
        "state": state,
        "mean_ms": statistics.mean(durations),
        "median_ms": statistics.median(durations),
        "p95_ms": percentile(durations, 0.95),
        "p99_ms": percentile(durations, 0.99),
        "max_ms": max(durations),
        "decision_counts": decisions,
        "external_meter_run_key": args.run_key,
        "calls_per_meter_interval": len(durations),
        "marker_telemetry": telemetry,
        "energy_accounting": "用整合INA226查询能耗.py取得该run_key的energy_j，再除以calls；净节能=基线能耗-方法E2E能耗，路由成本不得重复扣除。",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
