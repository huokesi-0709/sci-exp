from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="汇总先导查询的候选协议检索和路由运行结果。"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return round(ordered[index], 6)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    rows = read_jsonl(input_path)
    by_config: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_config[str(row["configuration"])].append(row)
        by_query[str(row["query_id"])].append(row)

    config_summary: dict[str, dict[str, Any]] = {}
    for config, config_rows in sorted(by_config.items()):
        latencies = [
            float(row["latency_ms"])
            for row in config_rows
            if row.get("latency_ms") is not None
        ]
        recalls = [
            float(row["metrics"]["retrieval_recall"])
            for row in config_rows
            if row["metrics"].get("retrieval_recall") is not None
        ]
        actions = [
            float(row["metrics"]["action_completeness"])
            for row in config_rows
            if row["metrics"].get("action_completeness") is not None
        ]
        config_summary[config] = {
            "runs": len(config_rows),
            "status_ok": sum(row.get("status") == "ok" for row in config_rows),
            "severe_failure": sum(
                bool(row["metrics"]["severe_failure"]) for row in config_rows
            ),
            "fallback": sum(bool(row["fallback"]) for row in config_rows),
            "fallback_correct": sum(
                bool(row["metrics"]["fallback_correct"]) for row in config_rows
            ),
            "retrieval_recall_observed": len(recalls),
            "retrieval_recall_mean": (
                round(statistics.mean(recalls), 6) if recalls else None
            ),
            "action_completeness_observed": len(actions),
            "action_completeness_mean": (
                round(statistics.mean(actions), 6) if actions else None
            ),
            "latency_p50_ms": percentile(latencies, 0.5),
            "latency_p95_ms": percentile(latencies, 0.95),
            "energy_measurement_values": sorted(
                {
                    str(row["telemetry"]["energy_measurement"])
                    for row in config_rows
                }
            ),
        }

    query_severity = {
        query_id: {
            "config_count": len(query_rows),
            "configs_with_severe_failure": [
                str(row["configuration"])
                for row in query_rows
                if row["metrics"]["severe_failure"]
            ],
            "all_configurations_severe": all(
                row["metrics"]["severe_failure"] for row in query_rows
            ),
        }
        for query_id, query_rows in sorted(by_query.items())
    }
    report = {
        "report_version": "pilot-run-summary-v0.1",
        "input": str(input_path),
        "run_count": len(rows),
        "query_count": len(by_query),
        "configuration_count": len(by_config),
        "formal_training_eligible": False,
        "metric_scope": "smoke_heuristic_not_publication_grade",
        "configurations": config_summary,
        "query_severity": query_severity,
        "queries_with_any_severe_failure": sum(
            bool(item["configs_with_severe_failure"])
            for item in query_severity.values()
        ),
        "queries_with_all_configurations_severe": sum(
            item["all_configurations_severe"]
            for item in query_severity.values()
        ),
        "limitations": [
            "候选协议仍未完成正式许可与版本冻结",
            "extractive后端不是正式生成模型",
            "energy_measurement为unavailable，不能报告物理能耗",
            "评价指标为Smoke启发式指标，不能替代人工安全评分",
        ],
    }
    output_json = Path(args.output_json).resolve()
    output_md = Path(args.output_md).resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    lines = [
        "# 先导运行摘要 v0.1",
        "",
        f"- 运行数：{report['run_count']}",
        f"- 查询数：{report['query_count']}",
        "- 配置：C0、C1、C2、C3",
        "- 正式训练资格：`false`",
        "",
        "| 配置 | 运行数 | 严重失效 | 回退 | 回退正确 | 检索召回均值 | 行动完整率均值 | P50时延(ms) | P95时延(ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for config, item in config_summary.items():
        recall = (
            f"{item['retrieval_recall_mean']:.3f}"
            if item["retrieval_recall_mean"] is not None
            else "NA"
        )
        action = (
            f"{item['action_completeness_mean']:.3f}"
            if item["action_completeness_mean"] is not None
            else "NA"
        )
        lines.append(
            "| {config} | {runs} | {severe_failure} | {fallback} | "
            "{fallback_correct} | {recall} | {action} | {latency_p50_ms:.3f} | "
            "{latency_p95_ms:.3f} |".format(
                config=config,
                recall=recall,
                action=action,
                **item,
            )
        )
    lines.extend(
        [
            "",
            f"- 至少一个配置严重失效的查询：{report['queries_with_any_severe_failure']}",
            f"- 所有配置均严重失效的查询：{report['queries_with_all_configurations_severe']}",
            "",
            "## 解释边界",
            "",
            "这是候选协议和extractive Smoke后端的工程诊断，不是正式实验结果。",
            "当前没有物理能耗测量，不能据此比较Radxa能耗；安全指标也只是启发式检查，",
            "不能替代双人/专家盲评。",
        ]
    )
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "run_count": report["run_count"],
                "query_count": report["query_count"],
                "output_json": str(output_json),
                "output_md": str(output_md),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
