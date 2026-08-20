from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="复核域外、L3、C3并重定义扩展候选source_group_id。"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--protocols", required=True)
    parser.add_argument("--license-table", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def event_cluster(text: str, disaster_type: str) -> str:
    if disaster_type == "general":
        return "out_of_scope"
    if any(token in text for token in ("呼吸", "喘", "吸不上气")):
        return "respiratory_distress"
    if any(token in text for token in ("流血", "出血", "血止不住")):
        return "severe_bleeding"
    if any(token in text for token in ("头", "头晕", "想吐")):
        return "head_injury"
    if any(token in text for token in ("重物", "压着", "压住", "卡住")):
        return "crush_or_entrapment"
    if any(token in text for token in ("墙", "掉东西", "掉下来", "余震")):
        return "collapse_or_aftershock"
    if any(token in text for token in ("冷", "发抖", "湿透", "失温")):
        return "cold_exposure"
    if any(token in text for token in ("没水", "没吃的", "很渴", "嘴很干")):
        return "resource_deprivation"
    if disaster_type == "operational_constraint":
        return "low_battery_communication"
    if disaster_type == "cross_disaster_support":
        return "psychological_distress"
    return disaster_type


def review_out_of_scope(row: dict[str, Any]) -> bool:
    return (
        row["disaster_type"] == "general"
        and row["query_type"] == "out_of_scope"
        and row["risk_level"] == 0
        and row["should_fallback"]
        and not row["gold_evidence_ids"]
        and row["expected_gap_control"]
    )


def review_l3(row: dict[str, Any]) -> bool:
    text = str(row["text"])
    high_risk_cue = (
        any(token in text for token in ("呼吸困难", "吸不上气", "喘不上气"))
        or (
            any(token in text for token in ("头晕", "想吐"))
            and any(token in text for token in ("流血", "出血", "血止不住"))
        )
    )
    return (
        row["risk_level"] == 3
        and high_risk_cue
        and bool(row["gold_evidence_ids"])
        and not row["evidence_gap_flag"]
    )


def review_fallback(row: dict[str, Any]) -> tuple[bool, str]:
    if row["expected_gap_control"]:
        return bool(row["should_fallback"]), "域外请求，必须回退"
    text = str(row["text"])
    if row["disaster_type"] == "operational_constraint":
        return bool(row["should_fallback"]), "设备约束，需转替代通信"
    if row["disaster_type"] == "cross_disaster_support":
        return bool(row["should_fallback"]), "支持性沟通需澄清并转专业支持"
    if any(token in text for token in ("没水", "没吃的", "很渴", "嘴很干")):
        return bool(row["should_fallback"]), "资源状态缺少时长、地点和症状"
    if row["evidence_gap_flag"]:
        return bool(row["should_fallback"]), "无适用协议证据"
    return not row["should_fallback"], "已有直接证据时不应无理由回退"


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    protocol_path = Path(args.protocols).resolve()
    license_path = Path(args.license_table).resolve()
    output_path = Path(args.output).resolve()
    report_path = Path(args.report).resolve()
    rows = read_jsonl(input_path)
    protocols = read_jsonl(protocol_path)
    protocol_by_evidence = {
        str(row["evidence_id"]): row for row in protocols
    }

    updated: list[dict[str, Any]] = []
    out_scope_checks: list[bool] = []
    l3_checks: list[bool] = []
    fallback_checks: list[bool] = []
    fallback_reasons: Counter[str] = Counter()

    for row in rows:
        evidence_rows = [
            protocol_by_evidence[evidence_id]
            for evidence_id in row["gold_evidence_ids"]
            if evidence_id in protocol_by_evidence
        ]
        families = sorted(
            {
                str(item.get("parent_source_id") or item["source_id"])
                for item in evidence_rows
            }
        )
        versions = sorted({str(item.get("version", "")) for item in evidence_rows})
        cluster = event_cluster(str(row["text"]), str(row["disaster_type"]))
        family = "+".join(families) if families else "NONE"
        version = "+".join(versions) if versions else "NONE"
        group_id = f"{cluster}|{family}|{version}"
        out_scope_ok = review_out_of_scope(row)
        l3_ok = review_l3(row)
        fallback_ok, fallback_reason = review_fallback(row)
        out_scope_checks.append(out_scope_ok)
        if row["risk_level"] == 3:
            l3_checks.append(l3_ok)
        if row["should_fallback"]:
            fallback_checks.append(fallback_ok)
            fallback_reasons[fallback_reason] += 1
        value = dict(row)
        value["source_group_id_legacy"] = value["source_group_id"]
        value["source_group_id"] = group_id
        value["event_cluster"] = cluster
        value["protocol_family"] = family
        value["protocol_version_chain"] = version
        value["freeze_review"] = {
            "out_of_scope_ok": out_scope_ok,
            "l3_ok": l3_ok if row["risk_level"] == 3 else None,
            "fallback_ok": fallback_ok if row["should_fallback"] else None,
            "fallback_reason": fallback_reason,
        }
        updated.append(value)

    license_rows = read_csv(license_path)
    license_blocked = [
        row["source_id"]
        for row in license_rows
        if row["再分发决定"] == "blocked_pending_manual_confirmation"
    ]
    version_uncleared = [
        row["source_id"]
        for row in license_rows
        if "仍需回到官方发布页核对" in row["版本日期证据"]
    ]
    report = {
        "report_version": "freeze-review-expansion-v0.1",
        "record_count": len(updated),
        "out_of_scope_count": sum(
            bool(row["expected_gap_control"]) for row in updated
        ),
        "out_of_scope_pass_count": sum(out_scope_checks),
        "l3_count": len(l3_checks),
        "l3_pass_count": sum(l3_checks),
        "fallback_count": len(fallback_checks),
        "fallback_pass_count": sum(fallback_checks),
        "fallback_reason_distribution": dict(fallback_reasons),
        "source_group_count": len(
            {row["source_group_id"] for row in updated}
        ),
        "license_freeze_pass": not license_blocked,
        "version_freeze_pass": not version_uncleared,
        "license_blocked_source_ids": license_blocked,
        "version_uncleared_source_ids": version_uncleared,
        "formal_library_freeze": False,
        "formal_training_eligible": False,
        "next_blockers": [
            "13份来源的许可与版本证据仍未全部完成",
            "当前source_group_id已按事件/协议/版本重算，但需领域审查确认",
            "双人一致性和专家仲裁尚未完成",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in updated
        ),
        encoding="utf-8",
        newline="\n",
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
