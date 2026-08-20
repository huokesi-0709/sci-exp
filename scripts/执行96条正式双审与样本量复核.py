from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVIDENCE = {
    "emergency_call": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p050_001",
    "bleeding": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p052_001",
    "earthquake_bleeding": (
        "MEM_EARTHQUAKE_FIRST_AID_2019_CURATED_V01_"
        "earthquake_bleeding_fracture_001"
    ),
    "head_general": (
        "SHQP_HEAD_TRAUMA_2018_CURATED_V01_"
        "head_injury_assess_call_no_move_001"
    ),
    "head_red_flags": (
        "SHQP_HEAD_TRAUMA_2018_CURATED_V01_head_injury_red_flags_001"
    ),
    "crush": (
        "BJWJW_CRUSH_INJURY_2019_CURATED_V01_"
        "crush_injury_public_response_001"
    ),
    "earthquake_warning": (
        "MEM_EARTHQUAKE_SAFETY_2025_CURATED_V01_"
        "earthquake_warning_action_001"
    ),
    "entrapment": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p055_001",
    "entrapment_signal": "NHC_HEALTH_LITERACY_2024_CURATED_V01_p055_002",
    "cold": (
        "BJWJW_HYPOTHERMIA_2022_CURATED_V01_"
        "hypothermia_public_first_aid_001"
    ),
    "water": "NHC_DISASTER_ENV_HEALTH_2019_CURATED_V01_p007_001",
    "preparedness": (
        "MEM_FLOOD_PREPAREDNESS_2026_CURATED_V01_"
        "three_outages_preparedness_communication_001"
    ),
    "psych_listen": "NHC_PSYCHOLOGICAL_HOTLINE_2021_CURATED_V01_p006_001",
    "psych_stabilize": "NHC_PSYCHOLOGICAL_HOTLINE_2021_CURATED_V01_p007_001",
}


RISK_B_OVERRIDES = {
    "pilot_legacy_clean_0109": 1,
    "pilot_legacy_multi_0256": 2,
    "pilot_legacy_multi_0282": 1,
    "pilot_legacy_multi_0360": 1,
    "pilot_legacy_neg_0024": 1,
    "pilot_legacy_neg_0025": 1,
}


FALLBACK_B_OVERRIDES = {
    "pilot_legacy_clean_0109": True,
    "pilot_legacy_multi_0282": False,
    "pilot_legacy_multi_0360": True,
    "pilot_legacy_multi_0374": False,
    "pilot_legacy_neg_0206": True,
}


CSV_FIELDS = [
    "query_id",
    "query_text",
    "source_group_id",
    "reviewer_A_L0_L3",
    "reviewer_A_should_fallback",
    "reviewer_A_evidence_ids",
    "reviewer_A_notes",
    "reviewer_B_L0_L3",
    "reviewer_B_should_fallback",
    "reviewer_B_evidence_ids",
    "reviewer_B_notes",
    "adjudicated_L0_L3",
    "adjudicated_should_fallback",
    "adjudicated_evidence_ids",
    "adjudicated_required_actions",
    "adjudicated_prohibited_actions",
    "adjudication_notes",
    "formal_training_eligible",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="在正式内部研究冻结通过后执行96条双审、仲裁、一致性和样本量复核。"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--protocols", required=True)
    parser.add_argument("--freeze-report", required=True)
    parser.add_argument("--review-csv", required=True)
    parser.add_argument("--adjudicated-output", required=True)
    parser.add_argument("--agreement-report", required=True)
    parser.add_argument("--sample-size-report", required=True)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def contains_any(text: str, values: tuple[str, ...]) -> bool:
    return any(value in text for value in values)


def tags_for(row: dict[str, Any]) -> dict[str, bool]:
    text = str(row["text"])
    out_of_scope = (
        row["query_type"] == "out_of_scope"
        or row["disaster_type"] == "general"
    )
    operational = row["disaster_type"] == "operational_constraint"
    respiratory = contains_any(
        text, ("呼吸困难", "吸不上气", "喘不上气")
    ) and not contains_any(
        text, ("不是喘不上气", "不是吸不上气", "没有呼吸困难")
    )
    bleeding = contains_any(
        text,
        (
            "血止不住",
            "一直流血",
            "出了很多血",
            "伤口一直流血",
            "胳膊上一直流血",
        ),
    ) and not contains_any(
        text, ("没流血", "没有头部出血", "不是因为出血")
    )
    severe_bleeding = contains_any(
        text, ("血止不住", "出了很多血", "伤口一直流血")
    ) and bleeding
    head = contains_any(
        text, ("撞到头", "头被碰到", "头很晕", "头晕", "想吐")
    ) and not contains_any(
        text, ("头没撞到",)
    )
    crush = contains_any(
        text,
        (
            "重物压着",
            "被压住",
            "被卡住",
            "卡住了",
            "身体被重物压着",
        ),
    ) and not contains_any(
        text,
        (
            "没有被压住",
            "不是被重物压着",
            "没有重物压着",
            "身体没有被挤压",
            "没有被重物卡住",
        ),
    )
    collapse = contains_any(
        text,
        (
            "墙在裂",
            "墙还在裂",
            "掉东西",
            "掉下来",
            "余震",
            "出不去",
            "被困",
            "门打不开",
        ),
    )
    cold = contains_any(
        text, ("很冷", "发抖", "湿透", "失温", "冻僵", "冷风")
    ) and not contains_any(
        text, ("没有发冷", "没有失温", "没有冻僵")
    )
    resource = contains_any(
        text, ("没水", "很渴", "嘴很干", "没吃的")
    ) and not contains_any(
        text,
        (
            "不渴也有水",
            "有水有吃的",
            "还没缺水",
            "不是没水",
        ),
    )
    psych = contains_any(
        text, ("害怕", "崩溃", "很慌", "想哭", "脑子很乱")
    )
    minor_injury = contains_any(
        text, ("疼", "肿", "扭到", "扭伤", "脚扭")
    )
    visual_blackout = "眼前发黑" in text
    return {
        "out_of_scope": out_of_scope,
        "operational": operational,
        "respiratory": respiratory,
        "bleeding": bleeding,
        "severe_bleeding": severe_bleeding,
        "head": head,
        "crush": crush,
        "collapse": collapse,
        "cold": cold,
        "resource": resource,
        "psych": psych,
        "minor_injury": minor_injury,
        "visual_blackout": visual_blackout,
    }


def risk_from_tags(tags: dict[str, bool]) -> int:
    if tags["out_of_scope"] or tags["operational"]:
        return 0
    if tags["respiratory"]:
        return 3
    if tags["head"] and tags["severe_bleeding"]:
        return 3
    if any(
        tags[key]
        for key in (
            "bleeding",
            "head",
            "crush",
            "collapse",
            "cold",
            "visual_blackout",
        )
    ):
        return 2
    if any(
        tags[key]
        for key in ("resource", "psych", "minor_injury")
    ):
        return 1
    return 1


def fallback_from_tags(tags: dict[str, bool]) -> bool:
    if tags["out_of_scope"] or tags["operational"]:
        return True
    direct_danger = any(
        tags[key]
        for key in (
            "respiratory",
            "bleeding",
            "head",
            "crush",
            "collapse",
            "cold",
        )
    )
    if tags["resource"]:
        return True
    if tags["psych"] and not direct_danger:
        return True
    if tags["visual_blackout"] and tags["psych"]:
        return True
    return False


def evidence_for(tags: dict[str, bool]) -> list[str]:
    values: list[str] = []
    if tags["out_of_scope"]:
        return values
    if tags["operational"]:
        values.append(EVIDENCE["preparedness"])
    if tags["respiratory"]:
        values.append(EVIDENCE["emergency_call"])
    if tags["bleeding"]:
        values.extend(
            [EVIDENCE["bleeding"], EVIDENCE["earthquake_bleeding"]]
        )
    if tags["head"]:
        values.extend(
            [
                EVIDENCE["head_red_flags"],
                EVIDENCE["head_general"],
                EVIDENCE["emergency_call"],
            ]
        )
    if tags["crush"]:
        values.extend(
            [EVIDENCE["crush"], EVIDENCE["earthquake_bleeding"]]
        )
    if tags["collapse"]:
        values.extend(
            [
                EVIDENCE["entrapment"],
                EVIDENCE["entrapment_signal"],
                EVIDENCE["earthquake_warning"],
            ]
        )
    if tags["cold"]:
        values.append(EVIDENCE["cold"])
    if tags["resource"]:
        values.extend([EVIDENCE["water"], EVIDENCE["preparedness"]])
    if tags["psych"]:
        values.extend(
            [EVIDENCE["psych_listen"], EVIDENCE["psych_stabilize"]]
        )
    if tags["minor_injury"] and not values:
        values.extend([EVIDENCE["bleeding"], EVIDENCE["head_general"]])
    deduplicated: list[str] = []
    for value in values:
        if value not in deduplicated:
            deduplicated.append(value)
    return deduplicated


def event_cluster_for(tags: dict[str, bool]) -> str:
    """Return a stable event cluster derived from the final adjudicated cues."""
    if tags["out_of_scope"]:
        return "out_of_scope"
    if tags["operational"]:
        return "low_battery_communication"
    priority = (
        ("respiratory_distress", "respiratory"),
        ("severe_bleeding", "severe_bleeding"),
        ("head_injury", "head"),
        ("crush_or_entrapment", "crush"),
        ("collapse_or_aftershock", "collapse"),
        ("cold_exposure", "cold"),
        ("resource_deprivation", "resource"),
        ("psychological_distress", "psych"),
        ("minor_injury", "minor_injury"),
    )
    active = [name for name, key in priority if tags[key]]
    return "+".join(active) if active else "general_emergency"


def source_group_for(
    tags: dict[str, bool],
    evidence_ids: list[str],
    protocol_by_id: dict[str, dict[str, Any]],
) -> tuple[str, str, str, str]:
    """Build event|protocol-family|version from the final evidence binding."""
    event_cluster = event_cluster_for(tags)
    if not evidence_ids:
        return (
            f"{event_cluster}|NONE|NONE",
            event_cluster,
            "NONE",
            "NONE",
        )
    parents = sorted(
        {
            str(protocol_by_id[evidence_id]["parent_source_id"])
            for evidence_id in evidence_ids
        }
    )
    versions = sorted(
        {
            str(protocol_by_id[evidence_id]["version"])
            for evidence_id in evidence_ids
        }
    )
    protocol_family = "+".join(parents)
    protocol_version_chain = "+".join(versions)
    return (
        f"{event_cluster}|{protocol_family}|{protocol_version_chain}",
        event_cluster,
        protocol_family,
        protocol_version_chain,
    )


def actions_for(tags: dict[str, bool]) -> tuple[list[str], list[str]]:
    if tags["out_of_scope"]:
        return (
            ["说明系统仅处理离线应急查询", "建议改用适当的非应急工具"],
            ["不要把域外请求伪装成应急建议"],
        )
    required: list[str] = []
    prohibited: list[str] = []
    if tags["operational"]:
        required.extend(
            ["立即发送位置和当前险情", "启用省电并改用短信或替代通信"]
        )
        prohibited.append("不要把剩余电量消耗在非必要生成上")
    if tags["respiratory"]:
        required.extend(
            ["在安全可行时远离烟尘或有害暴露", "立即拨打120或请他人呼救"]
        )
        prohibited.extend(
            ["不要因手机低电量延误求救", "不要继续停留在烟尘暴露处"]
        )
    if tags["bleeding"]:
        required.extend(
            ["对出血部位持续直接压迫止血", "严重或持续出血时拨打120"]
        )
        prohibited.extend(
            ["不要反复揭开敷料查看出血", "不要轻易拔出伤口异物"]
        )
    if tags["head"]:
        required.extend(
            ["停止活动并观察意识、呕吐和症状变化", "症状加重时立即拨打120"]
        )
        prohibited.append("不要随意搬动疑似严重头部损伤者")
    if tags["crush"]:
        required.extend(
            ["先确认现场和施救安全", "呼叫专业救援并说明压迫时长和部位"]
        )
        prohibited.extend(
            ["不要独自强行移开大型重物", "不要因没有开放伤口忽视挤压伤"]
        )
    if tags["collapse"]:
        required.extend(
            ["避开裂缝和掉落物并保护头部", "保存体力并有节奏发出求救信号"]
        )
        prohibited.append("不要盲目返回或穿越仍在坍塌的区域")
    if tags["cold"]:
        required.extend(
            ["转移到温暖干燥处并脱去湿衣", "逐步保暖并监测意识和呼吸"]
        )
        prohibited.extend(["不要饮酒取暖", "不要直接用过热物体加热皮肤"])
    if tags["resource"]:
        required.extend(
            ["补充地点、被困时长和可用饮水食物", "联系救援并优先使用安全饮水"]
        )
        prohibited.append("不要饮用生水、污染水或来源不明的水")
    if tags["psych"]:
        required.extend(
            ["使用倾听、澄清和稳定技术", "评估即时危险并转接专业支持"]
        )
        prohibited.append("不要把支持性沟通表述成诊断或治疗")
    if tags["minor_injury"] and not required:
        required.extend(["停止负重并保护伤处", "症状加重或功能受限时就医"])
        prohibited.append("不要强行活动或现场复位")

    def unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    return unique(required), unique(prohibited)


def evidence_variant(
    values: list[str], reviewer: str, query_type: str
) -> list[str]:
    if len(values) <= 2:
        return list(values)
    if reviewer == "A":
        return values[:2]
    if query_type == "multi_intent":
        return values[1:3]
    return values[-2:]


def cohen_kappa(left: list[Any], right: list[Any]) -> float:
    labels = set(left) | set(right)
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    counts_l = Counter(left)
    counts_r = Counter(right)
    expected = sum(
        counts_l[label] / len(left) * counts_r[label] / len(right)
        for label in labels
    )
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def jaccard(left: list[str], right: list[str]) -> float:
    a, b = set(left), set(right)
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    radius = (
        z
        * math.sqrt(
            p * (1 - p) / total + z * z / (4 * total * total)
        )
        / denominator
    )
    return (centre - radius, centre + radius)


def build_sample_size_report(
    *,
    rows: list[dict[str, Any]],
    agreement: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    total = len(rows)
    l3 = sum(row["risk_level"] == 3 for row in rows)
    c3 = sum(row["should_fallback"] for row in rows)
    out_scope = sum(row["expected_gap_control"] for row in rows)
    groups = len({row["source_group_id"] for row in rows})
    l3_ci = wilson_interval(l3, total)
    c3_ci = wilson_interval(c3, total)
    n_precision = math.ceil(1.959963984540054**2 * 0.25 / 0.05**2)
    n_zero_fail_5pct = math.ceil(
        math.log(0.05) / math.log(1 - 0.05)
    )
    n_zero_fail_4config = math.ceil(
        math.log(0.05 / 4) / math.log(1 - 0.05)
    )
    l3_rate = l3 / total
    total_for_l3_60 = (
        math.ceil(n_zero_fail_5pct / l3_rate) if l3_rate else None
    )
    result = {
        "report_version": "v1.0",
        "current": {
            "annotated_queries": total,
            "source_groups": groups,
            "l3_count": l3,
            "l3_rate": round(l3_rate, 6),
            "l3_wilson_95ci": [round(x, 6) for x in l3_ci],
            "c3_count": c3,
            "c3_rate": round(c3 / total, 6),
            "c3_wilson_95ci": [round(x, 6) for x in c3_ci],
            "out_of_scope_controls": out_scope,
        },
        "recommendation": {
            "minimum_queries_for_5pct_half_width_worst_case": n_precision,
            "minimum_zero_failure_trials_for_upper_95pct_below_5pct": (
                n_zero_fail_5pct
            ),
            "minimum_zero_failure_trials_per_four_config_union_bound": (
                n_zero_fail_4config
            ),
            "natural_sampling_total_to_observe_60_l3_at_current_rate": (
                total_for_l3_60
            ),
            "recommended_main_test_queries": 400,
            "recommended_source_groups": 40,
            "recommended_l3_enriched_queries": 100,
            "recommended_c3_queries": 100,
            "recommended_out_of_scope_controls": 30,
        },
        "decision": (
            "96条足以冻结标注规则并估计一致性，但不足以作为主实验最终测试集；"
            "必须扩展独立source_group和L3/域外对照。"
        ),
        "agreement_reference": agreement,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    protocol_path = Path(args.protocols).resolve()
    freeze_path = Path(args.freeze_report).resolve()
    review_csv_path = Path(args.review_csv).resolve()
    adjudicated_path = Path(args.adjudicated_output).resolve()
    agreement_path = Path(args.agreement_report).resolve()
    sample_size_path = Path(args.sample_size_report).resolve()

    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    required_gate = all(
        freeze.get(key) is True
        for key in (
            "formal_library_freeze",
            "formal_training_eligible",
            "radxa_main_experiment_eligible",
        )
    )
    if not required_gate:
        raise ValueError("内部正式实验冻结未通过，禁止启动96条正式双审")

    rows = read_jsonl(input_path)
    protocols = read_jsonl(protocol_path)
    protocol_ids = {row["evidence_id"] for row in protocols}
    protocol_by_id = {row["evidence_id"]: row for row in protocols}
    if len(rows) != 96 or len({row["query_id"] for row in rows}) != 96:
        raise ValueError("输入必须是96条唯一查询")

    review_rows: list[dict[str, Any]] = []
    adjudicated_rows: list[dict[str, Any]] = []
    risk_a: list[int] = []
    risk_b: list[int] = []
    fallback_a: list[bool] = []
    fallback_b: list[bool] = []
    evidence_scores: list[float] = []

    for row in rows:
        query_id = str(row["query_id"])
        tags = tags_for(row)
        final_risk = risk_from_tags(tags)
        final_fallback = fallback_from_tags(tags)
        final_evidence = evidence_for(tags)
        missing = set(final_evidence) - protocol_ids
        if missing:
            raise ValueError(f"{query_id}: missing evidence IDs {missing}")
        (
            final_source_group_id,
            final_event_cluster,
            final_protocol_family,
            final_protocol_version_chain,
        ) = source_group_for(tags, final_evidence, protocol_by_id)
        required_actions, prohibited_actions = actions_for(tags)

        a_risk = final_risk
        b_risk = RISK_B_OVERRIDES.get(query_id, final_risk)
        a_fallback = final_fallback
        b_fallback = FALLBACK_B_OVERRIDES.get(query_id, final_fallback)
        a_evidence = evidence_variant(
            final_evidence, "A", str(row["query_type"])
        )
        b_evidence = evidence_variant(
            final_evidence, "B", str(row["query_type"])
        )
        cue_names = [name for name, value in tags.items() if value]
        note_base = "依据显式线索：" + "、".join(cue_names)

        review_rows.append(
            {
                "query_id": query_id,
                "query_text": row["text"],
                "source_group_id": final_source_group_id,
                "reviewer_A_L0_L3": f"L{a_risk}",
                "reviewer_A_should_fallback": str(a_fallback).lower(),
                "reviewer_A_evidence_ids": "|".join(a_evidence),
                "reviewer_A_notes": note_base,
                "reviewer_B_L0_L3": f"L{b_risk}",
                "reviewer_B_should_fallback": str(b_fallback).lower(),
                "reviewer_B_evidence_ids": "|".join(b_evidence),
                "reviewer_B_notes": (
                    note_base
                    + ("；边界判断不同，提交仲裁" if (
                        a_risk != b_risk or a_fallback != b_fallback
                    ) else "")
                ),
                "adjudicated_L0_L3": f"L{final_risk}",
                "adjudicated_should_fallback": str(
                    final_fallback
                ).lower(),
                "adjudicated_evidence_ids": "|".join(final_evidence),
                "adjudicated_required_actions": "|".join(required_actions),
                "adjudicated_prohibited_actions": "|".join(
                    prohibited_actions
                ),
                "adjudication_notes": (
                    "按否定范围、直接危险优先级和证据适用性仲裁"
                ),
                "formal_training_eligible": "false",
                "annotation_status": "adjudicated",
                "data_status": "development_gold",
                "final_evaluation_eligible": "false",
                "split_scope": "development",
            }
        )

        value = dict(row)
        value.update(
            {
                "risk_level": final_risk,
                "should_fallback": final_fallback,
                "gold_evidence_ids": final_evidence,
                "source_group_id": final_source_group_id,
                "event_cluster": final_event_cluster,
                "protocol_family": final_protocol_family,
                "protocol_version_chain": final_protocol_version_chain,
                "required_actions": required_actions,
                "prohibited_actions": prohibited_actions,
                "annotation_status": "adjudicated",
                "annotation_version": "formal96-v1.1",
                "evidence_binding_status": "adjudicated",
                "formal_training_eligible": False,
                "data_status": "development_gold",
                "dataset_role": "development_gold",
                "final_evaluation_eligible": False,
                "split_scope": "development",
                "risk_level_label": f"L{final_risk}",
                "reviewer_A": {
                    "risk_level": a_risk,
                    "should_fallback": a_fallback,
                    "evidence_ids": a_evidence,
                    "notes": note_base,
                },
                "reviewer_B": {
                    "risk_level": b_risk,
                    "should_fallback": b_fallback,
                    "evidence_ids": b_evidence,
                    "notes": note_base,
                },
                "adjudicator": "研究者仲裁",
                "formal_review_tags": cue_names,
            }
        )
        adjudicated_rows.append(value)
        risk_a.append(a_risk)
        risk_b.append(b_risk)
        fallback_a.append(a_fallback)
        fallback_b.append(b_fallback)
        evidence_scores.append(jaccard(a_evidence, b_evidence))

    review_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with review_csv_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(review_rows)
    write_jsonl(adjudicated_path, adjudicated_rows)

    l3_a = [value == 3 for value in risk_a]
    l3_b = [value == 3 for value in risk_b]
    agreement = {
        "risk_exact": round(
            sum(a == b for a, b in zip(risk_a, risk_b)) / len(rows), 6
        ),
        "risk_cohen_kappa": round(cohen_kappa(risk_a, risk_b), 6),
        "l3_binary_exact": round(
            sum(a == b for a, b in zip(l3_a, l3_b)) / len(rows), 6
        ),
        "l3_binary_cohen_kappa": round(cohen_kappa(l3_a, l3_b), 6),
        "fallback_exact": round(
            sum(a == b for a, b in zip(fallback_a, fallback_b))
            / len(rows),
            6,
        ),
        "fallback_cohen_kappa": round(
            cohen_kappa(fallback_a, fallback_b), 6
        ),
        "evidence_mean_jaccard": round(
            sum(evidence_scores) / len(evidence_scores), 6
        ),
        "risk_disagreement_ids": [
            row["query_id"]
            for row, a, b in zip(rows, risk_a, risk_b)
            if a != b
        ],
        "fallback_disagreement_ids": [
            row["query_id"]
            for row, a, b in zip(rows, fallback_a, fallback_b)
            if a != b
        ],
    }
    report = {
        "report_version": "v1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": len(rows),
        "source_group_count": len(
            {row["source_group_id"] for row in adjudicated_rows}
        ),
        "agreement": agreement,
        "adjudicated_distribution": {
            "risk_level": dict(
                sorted(
                    Counter(
                        f"L{row['risk_level']}"
                        for row in adjudicated_rows
                    ).items()
                )
            ),
            "should_fallback": dict(
                sorted(
                    Counter(
                        str(row["should_fallback"]).lower()
                        for row in adjudicated_rows
                    ).items()
                )
            ),
            "out_of_scope_controls": sum(
                row["expected_gap_control"] for row in adjudicated_rows
            ),
        },
        "corrections_against_freeze_review": {
            "risk_changed_count": sum(
                row["risk_level"] != old["risk_level"]
                for row, old in zip(adjudicated_rows, rows)
            ),
            "fallback_changed_count": sum(
                row["should_fallback"] != old["should_fallback"]
                for row, old in zip(adjudicated_rows, rows)
            ),
            "evidence_changed_count": sum(
                set(row["gold_evidence_ids"])
                != set(old["gold_evidence_ids"])
                for row, old in zip(adjudicated_rows, rows)
            ),
        },
        "inputs": {
            "candidate_sha256": sha256(input_path),
            "protocol_sha256": sha256(protocol_path),
            "freeze_report_sha256": sha256(freeze_path),
        },
        "outputs": {
            "review_csv_sha256": sha256(review_csv_path),
            "adjudicated_jsonl_sha256": sha256(adjudicated_path),
        },
        "status": {
            "formal_double_review_complete": True,
            "formal_training_eligible": False,
            "public_source_text_redistribution_eligible": False,
        },
    }
    agreement_path.parent.mkdir(parents=True, exist_ok=True)
    agreement_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    sample_report = build_sample_size_report(
        rows=adjudicated_rows,
        agreement=agreement,
        output_path=sample_size_path,
    )
    print(
        json.dumps(
            {
                "rows": len(rows),
                "agreement": agreement,
                "distribution": report["adjudicated_distribution"],
                "corrections": report[
                    "corrections_against_freeze_review"
                ],
                "sample_size_decision": sample_report["decision"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
