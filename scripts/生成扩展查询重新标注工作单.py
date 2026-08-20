from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "query_id",
    "text",
    "language",
    "旧标签提示_灾种",
    "旧标签提示_查询类型",
    "旧标签提示_风险等级",
    "旧标签提示_回退",
    "旧标签提示_扰动类型",
    "当前灾种",
    "当前查询类型",
    "当前风险等级_L0_L3",
    "当前是否C3回退",
    "当前gold_evidence_ids",
    "必需行动",
    "禁止行动",
    "协议家族",
    "协议版本",
    "辖区",
    "证据空白",
    "标注者A",
    "日期A",
    "标注者B",
    "日期B",
    "仲裁者",
    "仲裁日期",
    "最终状态",
    "备注",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成96条扩展候选的独立重新标注工作单。"
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


def json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    rows = read_jsonl(input_path)
    output_rows: list[dict[str, str]] = []
    for row in rows:
        hint = row.get("legacy_hint", {})
        output_rows.append(
            {
                "query_id": str(row["query_id"]),
                "text": str(row["text"]),
                "language": str(row.get("language", "")),
                "旧标签提示_灾种": str(hint.get("disaster_type", "")),
                "旧标签提示_查询类型": str(hint.get("query_type", "")),
                "旧标签提示_风险等级": str(hint.get("risk_level", "")),
                "旧标签提示_回退": str(hint.get("should_fallback", "")),
                "旧标签提示_扰动类型": json_cell(
                    hint.get("legacy_perturbation_types", [])
                ),
                "当前灾种": "",
                "当前查询类型": "",
                "当前风险等级_L0_L3": "",
                "当前是否C3回退": "",
                "当前gold_evidence_ids": "",
                "必需行动": "",
                "禁止行动": "",
                "协议家族": "",
                "协议版本": "",
                "辖区": "",
                "证据空白": "",
                "标注者A": "",
                "日期A": "",
                "标注者B": "",
                "日期B": "",
                "仲裁者": "",
                "仲裁日期": "",
                "最终状态": "待独立重新标注",
                "备注": "旧标签仅供采样分层参考，不得复制到当前字段",
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(output_rows)
    print(
        json.dumps(
            {
                "input_rows": len(rows),
                "output_rows": len(output_rows),
                "output": str(output_path),
                "formal_training_eligible": False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
