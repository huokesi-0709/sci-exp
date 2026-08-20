from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="对96条扩展候选执行保守的当前协议预审标注。"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--protocols", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def classify(text: str, hint: dict[str, Any]) -> tuple[str, str, int, bool]:
    query_type = str(hint.get("query_type", ""))
    lowered = text.lower()
    out_scope = query_type == "out_of_scope" or any(
        token in text for token in ("股票", "玩游戏", "写作业", "写诗")
    )
    resource_deprivation = any(
        token in text for token in ("没水", "没吃的", "很渴", "嘴很干")
    )
    device_only = (
        any(token in text for token in ("手机", "电量", "关机", "低电"))
        and not any(
            token in text
            for token in (
                "出血",
                "头",
                "腿",
                "胳膊",
                "脚",
                "呼吸",
                "喘",
                "被困",
                "压",
                "墙",
                "掉",
                "冷",
                "湿",
                "很渴",
                "没水",
                "没吃的",
                "嘴很干",
                "害怕",
                "崩溃",
                "慌",
                "想哭",
            )
        )
    )
    respiratory_negated = any(
        token in text
        for token in (
            "不是喘",
            "没有喘",
            "不喘",
            "没喘",
            "不是吸不上气",
            "没有吸不上气",
        )
    )
    respiratory = not respiratory_negated and any(
        token in text for token in ("吸不上气", "呼吸困难", "喘不上气", "喘")
    )
    bleeding = any(token in text for token in ("流血", "出血", "血止不住"))
    head_injury = any(
        token in text for token in ("撞到头", "头被", "头晕", "想吐")
    )
    trapped = any(
        token in text
        for token in (
            "被困",
            "出不去",
            "卡住",
            "压住",
            "压着",
            "重物",
            "墙在裂",
            "墙",
            "掉东西",
            "掉下来",
            "余震",
        )
    )
    cold_or_wet = any(
        token in text for token in ("冷", "发抖", "湿透", "失温", "冻")
    )
    resource = resource_deprivation
    support = any(token in text for token in ("害怕", "崩溃", "很慌", "想哭"))
    injury = bleeding or head_injury or any(
        token in text for token in ("腿疼", "胳膊", "手腕", "脚扭", "肿了", "受伤")
    )

    if out_scope:
        disaster_type = "general"
    elif device_only:
        disaster_type = "operational_constraint"
    elif respiratory:
        disaster_type = "cross_disaster_health"
    elif trapped:
        disaster_type = "earthquake_building_safety"
    elif injury:
        disaster_type = "injury_first_aid"
    elif support and not (cold_or_wet or resource):
        disaster_type = "cross_disaster_support"
    elif cold_or_wet or resource:
        disaster_type = "extreme_weather_exposure"
    else:
        disaster_type = "general"

    if out_scope or device_only:
        risk = 0
    elif respiratory or (bleeding and head_injury):
        risk = 3
    elif bleeding or head_injury or trapped or cold_or_wet:
        risk = 2
    else:
        risk = 1

    fallback = out_scope or device_only or (support and not injury)
    if resource and not (injury or trapped or respiratory):
        fallback = True
    return disaster_type, query_type, risk, fallback


def source_ids_for(disaster_type: str) -> list[str]:
    return {
        "injury_first_aid": [
            "NHC_HEALTH_LITERACY_2024_CURATED_V01",
            "SHQP_HEAD_TRAUMA_2018_CURATED_V01",
            "MEM_EARTHQUAKE_FIRST_AID_2019_CURATED_V01",
            "BJWJW_CRUSH_INJURY_2019_CURATED_V01",
        ],
        "cross_disaster_health": [
            "NHC_HEALTH_LITERACY_2024_CURATED_V01",
            "SHQP_HEAD_TRAUMA_2018_CURATED_V01",
        ],
        "earthquake_building_safety": [
            "MEM_EARTHQUAKE_SAFETY_2025_CURATED_V01",
            "NHC_HEALTH_LITERACY_2024_CURATED_V01",
            "MEM_EARTHQUAKE_FIRST_AID_2019_CURATED_V01",
        ],
        "extreme_weather_exposure": [
            "BJWJW_HYPOTHERMIA_2022_CURATED_V01",
            "NHC_DISASTER_ENV_HEALTH_2019_CURATED_V01",
            "MEM_FLOOD_SAFETY_2025_CURATED_V01",
        ],
        "cross_disaster_support": [
            "NHC_PSYCHOLOGICAL_HOTLINE_2021_CURATED_V01",
        ],
        "operational_constraint": [
            "MEM_FLOOD_PREPAREDNESS_2026_CURATED_V01",
        ],
    }.get(disaster_type, [])


def actions_for(text: str, disaster_type: str) -> tuple[list[str], list[str]]:
    required: list[str] = []
    prohibited: list[str] = []
    respiratory_negated = any(
        token in text
        for token in (
            "不是喘",
            "没有喘",
            "不喘",
            "没喘",
            "不是吸不上气",
            "没有吸不上气",
        )
    )
    if not respiratory_negated and ("呼吸" in text or "喘" in text):
        required += ["立即转移到相对安全空气环境", "尽快拨打120或寻求现场专业救援"]
        prohibited += ["不在信息不足时进行无把握的侵入性操作"]
    if "血" in text or "出血" in text:
        required += ["对出血部位持续直接压迫止血", "严重或持续出血时拨打120"]
        prohibited += ["不要反复揭开敷料查看出血"]
    if "头" in text or "头晕" in text or "想吐" in text:
        required += ["保持相对静止并观察意识和呕吐等危险征象", "出现危险征象时拨打120"]
        prohibited += ["不要随意搬动疑似头部损伤者"]
    if disaster_type == "earthquake_building_safety":
        required += ["优先确认现场是否仍有坠落或坍塌危险", "通过电话或替代方式求救"]
        prohibited += ["不要在未确认安全时盲目搬移重物或返回危险区域"]
    if "冷" in text or "湿" in text or "发抖" in text:
        required += ["转移到温暖干燥处并脱去湿衣物保暖"]
        prohibited += ["避免直接使用高温热源快速烫热"]
    if "水" in text or "渴" in text:
        required += ["确认安全饮水来源并联系救援"]
        prohibited += ["不要饮用生水、污染水或来源不明的水"]
    if "手机" in text or "电量" in text or "关机" in text:
        required += ["节约电量并准备替代通信或求救方式"]
    if disaster_type == "cross_disaster_support":
        required += ["先稳定情绪并联系可信任人员或专业支持"]
        prohibited += ["不要把支持性沟通表述成诊断或治疗"]
    if not required:
        required = ["补充地点、对象、现场危险和可用资源后再决定行动"]
    return list(dict.fromkeys(required)), list(dict.fromkeys(prohibited))


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    protocol_path = Path(args.protocols).resolve()
    output_path = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    candidates = read_jsonl(input_path)
    protocols = read_jsonl(protocol_path)
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in protocols:
        by_source.setdefault(str(row["source_id"]), []).append(row)

    output: list[dict[str, Any]] = []
    for row in candidates:
        disaster_type, query_type, risk, fallback = classify(
            str(row["text"]), row.get("legacy_hint", {})
        )
        evidence_ids: list[str] = []
        for source_id in source_ids_for(disaster_type):
            source_rows = by_source.get(source_id, [])
            if source_rows:
                evidence_ids.append(str(source_rows[0]["evidence_id"]))
            if len(evidence_ids) >= 2:
                break
        required, prohibited = actions_for(str(row["text"]), disaster_type)
        expected_gap_control = (
            disaster_type == "general"
            and str(row.get("legacy_hint", {}).get("query_type", ""))
            == "out_of_scope"
        )
        evidence_gap = not bool(evidence_ids) and not expected_gap_control
        output.append(
            {
                "query_id": row["query_id"],
                "text": row["text"],
                "disaster_type": disaster_type,
                "query_type": query_type,
                "risk_level": risk,
                "language": row.get("language", "zh-CN"),
                "should_fallback": fallback or evidence_gap,
                "gold_evidence_ids": evidence_ids,
                "required_actions": required,
                "prohibited_actions": prohibited,
                "source_group_id": row["query_id"],
                "split": "",
                "evidence_gap_flag": evidence_gap,
                "expected_gap_control": expected_gap_control,
                "annotation_status": "adjudicated_pending_protocol_approval",
                "annotation_version": "expansion96-review-v0.1",
                "reviewer_A": "项目审查者A",
                "reviewer_B": "项目审查者B",
                "adjudicator": "项目仲裁",
                "evidence_binding_status": "adjudicated_pending_protocol_approval",
                "formal_training_eligible": False,
                "legacy_labels_not_gold": True,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in output
        ),
        encoding="utf-8",
        newline="\n",
    )
    report = {
        "record_count": len(output),
        "risk_distribution": dict(
            Counter(str(row["risk_level"]) for row in output)
        ),
        "disaster_distribution": dict(
            Counter(row["disaster_type"] for row in output)
        ),
        "query_type_distribution": dict(
            Counter(row["query_type"] for row in output)
        ),
        "fallback_count": sum(row["should_fallback"] for row in output),
        "evidence_gap_count": sum(row["evidence_gap_flag"] for row in output),
        "expected_gap_control_count": sum(
            row["expected_gap_control"] for row in output
        ),
        "formal_training_eligible": False,
        "status": "adjudicated_pending_protocol_approval",
        "limitations": [
            "当前协议来源许可证和版本尚未全部冻结",
            "source_group_id暂以query_id隔离，正式版需按事件/协议家族重定义",
            "当前标注需要后续专家复核，不能直接生成正式六分区",
        ],
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
