from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="审计先导查询的灾种、风险、类型和回退覆盖，并生成扩展采样计划。"
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


def counts(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(
        sorted(
            Counter(str(row.get(field, "")) for row in rows).items(),
            key=lambda item: (-item[1], item[0]),
        )
    )


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    rows = read_jsonl(input_path)
    target_total = 120
    target_min_per_disaster = 8
    target_min_per_query_type = 8
    target_min_per_risk_level = 15

    disaster_counts = counts(rows, "disaster_type")
    query_type_counts = counts(rows, "query_type")
    risk_counts = counts(rows, "risk_level")
    fallback_counts = counts(
        [
            {**row, "fallback": str(bool(row.get("should_fallback"))).lower()}
            for row in rows
        ],
        "fallback",
    )
    short_challenge_count = sum(
        bool(row.get("preprocessing", {}).get("short_query_challenge"))
        for row in rows
    )
    evidence_gap_count = sum(bool(row.get("evidence_gap_flag")) for row in rows)

    disaster_additions = {
        key: max(0, target_min_per_disaster - value)
        for key, value in disaster_counts.items()
    }
    query_type_additions = {
        key: max(0, target_min_per_query_type - value)
        for key, value in query_type_counts.items()
    }
    risk_additions = {
        key: max(0, target_min_per_risk_level - value)
        for key, value in risk_counts.items()
    }
    remaining = max(0, target_total - len(rows))
    report = {
        "report_version": "pilot-coverage-v0.1",
        "input": str(input_path),
        "pilot_count": len(rows),
        "provisional_target_count": target_total,
        "provisional_additional_count": remaining,
        "counts": {
            "disaster_type": disaster_counts,
            "query_type": query_type_counts,
            "risk_level": risk_counts,
            "should_fallback": fallback_counts,
        },
        "special_coverage": {
            "short_query_challenge": short_challenge_count,
            "evidence_gap": evidence_gap_count,
        },
        "minimum_quota_assumptions": {
            "disaster_type_minimum": target_min_per_disaster,
            "query_type_minimum": target_min_per_query_type,
            "risk_level_minimum": target_min_per_risk_level,
        },
        "minimum_quota_additions": {
            "disaster_type": disaster_additions,
            "query_type": query_type_additions,
            "risk_level": risk_additions,
        },
        "next_sampling_priorities": [
            "优先补齐当前样本数低于灾种最小配额的灾种",
            "为clean_control、multi_intent、negation_conflict和out_of_scope分别补齐至少8条",
            "将L0、L1、L2、L3分别补齐到至少15条，再按正式功效分析修订",
            "保留短查询挑战集，但单独记录其比例和风险分层",
            "增加证据不足、版本冲突和错误辖区查询，不把机器检索结果当作标签",
            "每个新增查询登记来源组、协议版本、查询生成方式和人工审核状态",
        ],
        "limitations": [
            "配额是先导扩展计划，不是最终正式样本量计算结果",
            "当前24条仍不能用于正式训练、校准或测试",
            "许可证和协议版本冻结完成前，不生成正式gold数据",
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
        "# 先导查询覆盖审计与扩展采样计划 v0.1",
        "",
        f"- 当前先导查询：{len(rows)}条",
        f"- 临时扩展目标：{target_total}条",
        f"- 建议新增：{remaining}条",
        "",
        "## 当前覆盖",
        "",
        "| 维度 | 分布 |",
        "|---|---|",
        f"| 灾种 | {disaster_counts} |",
        f"| 查询类型 | {query_type_counts} |",
        f"| 风险等级 | {risk_counts} |",
        f"| 回退 | {fallback_counts} |",
        f"| 短查询挑战 | {short_challenge_count} |",
        f"| 证据空白 | {evidence_gap_count} |",
        "",
        "## 扩展原则",
        "",
    ]
    lines.extend(f"- {item}" for item in report["next_sampling_priorities"])
    lines.extend(
        [
            "",
            "## 使用边界",
            "",
            "这是下一批先导查询的采样计划，不是正式数据集，也不是最终样本量结论。",
            "完成许可、版本、标注指南和专家复核后，才可将扩展数据升级为正式数据候选。",
        ]
    )
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "pilot_count": len(rows),
                "provisional_target_count": target_total,
                "provisional_additional_count": remaining,
                "output_json": str(output_json),
                "output_md": str(output_md),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
