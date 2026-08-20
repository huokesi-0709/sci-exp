from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="汇总C0-C3开发诊断，禁止作为论文结果")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def mean_optional(values: list[object]) -> float | None:
    numeric = [float(value) for value in values if value is not None]
    return statistics.fmean(numeric) if numeric else None


def main() -> int:
    args = parse_args()
    rows = read_rows(args.input)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("configuration", ""))].append(row)
    summary: dict[str, dict[str, object]] = {}
    for configuration, items in sorted(grouped.items()):
        latencies = [float(item["latency_ms"]) for item in items]
        evidence_counts = [len(item.get("evidence_ids", [])) for item in items]
        fallback_count = sum(bool(item.get("fallback")) for item in items)
        second_steps = sum(
            item.get("retrieval_diagnostics", {}).get("retrieval_steps") == 2
            for item in items
        )
        conflict_count = sum(
            bool(item.get("retrieval_diagnostics", {}).get("conflicts"))
            for item in items
        )
        summary[configuration] = {
            "runs": len(items),
            "success_rate": sum(item.get("status") == "ok" for item in items)
            / len(items),
            "latency_ms_median": statistics.median(latencies),
            "latency_ms_p95": sorted(latencies)[
                min(len(latencies) - 1, int(0.95 * len(latencies)))
            ],
            "mean_evidence_count": statistics.fmean(evidence_counts),
            "fallback_rate": fallback_count / len(items),
            "mean_smoke_retrieval_recall": mean_optional(
                [item.get("metrics", {}).get("retrieval_recall") for item in items]
            ),
            "mean_smoke_action_completeness": mean_optional(
                [
                    item.get("metrics", {}).get("action_completeness")
                    for item in items
                ]
            ),
            "second_step_rate": second_steps / len(items),
            "candidate_conflict_rate": conflict_count / len(items),
            "generator_backends": sorted(
                {str(item.get("generator_backend", "")) for item in items}
            ),
        }
    evidence_means = {
        key: value["mean_evidence_count"] for key, value in summary.items()
    }
    structural_difference = (
        evidence_means.get("C0") == 0
        and evidence_means.get("C3") == 0
        and float(evidence_means.get("C1", 0)) > 0
        and float(evidence_means.get("C2", 0)) > 0
        and evidence_means.get("C1") != evidence_means.get("C2")
    )
    report = {
        "schema_version": "configuration-development-diagnostic-v1.0",
        "input": str(args.input),
        "scope": "cal_op_development_only",
        "backend_warning": (
            "使用hashing-development与extractive-smoke；这里只验证代码路径和结构差异，"
            "不能作为论文质量、风险、时延或能耗结果。"
        ),
        "by_configuration": summary,
        "gates": {
            "all_four_configurations_present": set(summary)
            == {"C0", "C1", "C2", "C3"},
            "structural_retrieval_difference_present": structural_difference,
            "real_generator_difference_verified": False,
            "physical_resource_difference_verified": False,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["gates"], ensure_ascii=False))
    return 0 if all(
        [
            report["gates"]["all_four_configurations_present"],
            report["gates"]["structural_retrieval_difference_present"],
        ]
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
