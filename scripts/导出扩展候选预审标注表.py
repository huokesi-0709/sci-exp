from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "query_id",
    "text",
    "灾种",
    "查询类型",
    "风险等级_L0_L3",
    "是否C3回退",
    "gold_evidence_ids",
    "必需行动",
    "禁止行动",
    "source_group_id",
    "证据空白",
    "预期域外空白",
    "标注状态",
    "标注版本",
    "正式训练资格",
    "备注",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将扩展候选预审JSONL导出为可审阅CSV。"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def cell(value: Any) -> str:
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value if value is not None else "")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    rows = read_jsonl(input_path)
    output_rows = [
        {
            "query_id": row["query_id"],
            "text": row["text"],
            "灾种": row["disaster_type"],
            "查询类型": row["query_type"],
            "风险等级_L0_L3": row["risk_level"],
            "是否C3回退": cell(row["should_fallback"]),
            "gold_evidence_ids": cell(row["gold_evidence_ids"]),
            "必需行动": cell(row["required_actions"]),
            "禁止行动": cell(row["prohibited_actions"]),
            "source_group_id": row["source_group_id"],
            "证据空白": cell(row["evidence_gap_flag"]),
            "预期域外空白": cell(row["expected_gap_control"]),
            "标注状态": row["annotation_status"],
            "标注版本": row["annotation_version"],
            "正式训练资格": cell(row["formal_training_eligible"]),
            "备注": "预审结果；协议许可、版本和专家复核完成前不得进入正式数据",
        }
        for row in rows
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)
    print(
        json.dumps(
            {"rows": len(output_rows), "output": str(output_path)},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
