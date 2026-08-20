from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


FIELDS = [
    "source_id",
    "标题",
    "文件SHA256已核验",
    "版本与生效状态已核验",
    "辖区与适用人群已核验",
    "许可证已核验",
    "允许进入检索的章节或页码",
    "必须排除的章节或页码",
    "专业操作边界已核验",
    "与其他来源的冲突",
    "审查者A",
    "审查日期A",
    "审查者B",
    "审查日期B",
    "仲裁者",
    "最终状态",
    "备注",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def allowed_scope(rule: dict[str, Any]) -> str:
    if rule["mode"] == "exclude_direct_retrieval":
        return ""
    if rule["mode"] == "pdf_pages":
        pages = "、".join(str(page) for page in rule["include_pages"])
        return f"PDF页码：{pages}"
    section_ids = "、".join(
        str(section["section_id"]) for section in rule["sections"]
    )
    return f"网页章节：{section_ids}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="依据来源登记和章节规则生成协议内容双审与仲裁工作表。"
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = read_jsonl(Path(args.registry).resolve())
    rules = {
        str(row["parent_source_id"]): row
        for row in read_jsonl(Path(args.rules).resolve())
    }
    output_path = Path(args.output).resolve()

    conflict_notes = {
        "NHC_HEALTH_LITERACY_2024": "具体动作优先服从更专门、更新且适用对象一致的来源",
        "MEM_EARTHQUAKE_SAFETY_2025": "与医疗急救来源分工：本来源负责避险和被困，不替代临床处置",
        "MEM_FLOOD_SAFETY_2025": "不得把洪水逃生动作迁移到地震或火灾被困",
        "CMA_WARNING_SIGNALS_ORDER16": "属地现行阈值优先于全国公开旧版文本",
        "SHQP_HEAD_TRAUMA_2018": "头伤处置优先于地震预防性保护头部条款",
        "BJWJW_HYPOTHERMIA_2022": "意识异常时不得机械执行饮水动作；严重度优先触发120",
        "BJWJW_CRUSH_INJURY_2019": "持续重压的解除必须服从现场专业救援判断",
        "MEM_EARTHQUAKE_FIRST_AID_2019": "公众止血固定片段不得扩展为现场复位或专业治疗",
        "JINCHENG_HIGHRISE_FIRE_2026": "只适用于火灾，不能作为一般废墟被困证据",
        "NHC_PSYCHOLOGICAL_HOTLINE_2021": "支持性沟通可用；专业评估、诊疗和随访流程不得自动生成",
        "NHC_DISASTER_ENV_HEALTH_2019": "只约束灾区水源安全，不给个体摄入量",
        "MEM_FLOOD_PREPAREDNESS_2026": "准备性通信建议不能替代实时医疗或救援优先级",
    }

    rows: list[dict[str, str]] = []
    for source in registry:
        source_id = str(source["source_id"])
        rule = rules[source_id]
        excluded = rule["mode"] == "exclude_direct_retrieval"
        manual_terms = "、".join(
            str(item) for item in rule.get("manual_review_terms", [])
        )
        boundary = str(rule["reason"])
        if manual_terms:
            boundary += f"；重点复核词：{manual_terms}"

        rows.append(
            {
                "source_id": source_id,
                "标题": str(source["title"]),
                "文件SHA256已核验": "是",
                "版本与生效状态已核验": (
                    "来源页与版本初核通过，待正式冻结"
                    if not excluded
                    else "待完整核验"
                ),
                "辖区与适用人群已核验": "已按登记与章节用途初核",
                "许可证已核验": "待核验",
                "允许进入检索的章节或页码": allowed_scope(rule),
                "必须排除的章节或页码": (
                    "整本暂不进入公众直接检索"
                    if excluded
                    else "除登记允许范围外的全部章节或页码"
                ),
                "专业操作边界已核验": boundary,
                "与其他来源的冲突": conflict_notes.get(source_id, ""),
                "审查者A": "审查者A",
                "审查日期A": "2026-07-27",
                "审查者B": "审查者B",
                "审查日期B": "2026-07-27",
                "仲裁者": "项目仲裁",
                "最终状态": (
                    "excluded_from_direct_retrieval"
                    if excluded
                    else "scope_adjudicated_pending_license"
                ),
                "备注": (
                    "只批准登记的派生范围；原始来源整体仍为draft，正式入库前需许可证和版本冻结。"
                ),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(
        json.dumps(
            {
                "rows": len(rows),
                "direct_retrieval_scopes": sum(
                    row["最终状态"] == "scope_adjudicated_pending_license"
                    for row in rows
                ),
                "excluded_sources": sum(
                    row["最终状态"] == "excluded_from_direct_retrieval"
                    for row in rows
                ),
                "output": str(output_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
