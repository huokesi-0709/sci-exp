from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sci_exp.retrieval import BM25Index  # noqa: E402
from sci_exp.schemas import ProtocolChunk  # noqa: E402


INTENT_QUOTAS = {
    "severe_bleeding_or_shock": 3,
    "trauma_or_fracture": 3,
    "altered_consciousness_or_head_injury": 2,
    "respiratory_distress": 3,
    "hypothermia": 2,
    "trapped_or_entrapment": 3,
    "aftershock_or_collapse_hazard": 2,
    "crush_injury": 2,
    "dehydration_or_resource_deprivation": 1,
    "psychological_distress": 1,
    "low_battery": 1,
    "out_of_scope": 1,
}
INTENT_HAZARDS = {
    "severe_bleeding_or_shock": {"severe_bleeding"},
    "trauma_or_fracture": {"fracture"},
    "altered_consciousness_or_head_injury": {
        "head_injury",
        "altered_consciousness",
        "emergency_call",
        "earthquake",
    },
    "respiratory_distress": {"emergency_call", "choking"},
    "hypothermia": {"hypothermia", "cold_exposure", "cold_wave"},
    "trapped_or_entrapment": {
        "earthquake",
        "highrise_entrapment",
        "entrapment",
        "smoke_exposure",
        "fire",
        "flood",
    },
    "aftershock_or_collapse_hazard": {"earthquake", "aftershock", "collapse"},
    "crush_injury": {"crush_injury", "fracture", "emergency_call"},
    "dehydration_or_resource_deprivation": {
        "drinking_water",
        "water_contamination",
    },
    "psychological_distress": {"psychological_distress"},
    "low_battery": {
        "power_outage",
        "network_outage",
        "communication",
        "preparedness",
    },
    "out_of_scope": set(),
}
INTENT_RETRIEVAL_HINTS = {
    "severe_bleeding_or_shock": "创伤 出血 止血 包扎",
    "trauma_or_fracture": "创伤 骨折 受伤 不要随意搬动",
    "altered_consciousness_or_head_injury": "头部受伤 头晕 意识 急救电话",
    "respiratory_distress": "呼吸困难 窒息 急救电话",
    "hypothermia": "低温症 失温 湿冷 暴露 防寒 保暖",
    "trapped_or_entrapment": "被困 逃生 避险 疏散",
    "aftershock_or_collapse_hazard": "地震 余震 倒塌 避险",
    "crush_injury": "重物 压伤 骨折 急救电话",
    "dehydration_or_resource_deprivation": "灾区 饮用水 生水 污染 水源",
    "psychological_distress": "心理困扰 倾听 稳定 情绪 支持",
    "low_battery": "断电 断网 低电量 充电宝 应急通信 联络",
    "out_of_scope": "",
}
QUERY_TYPE_ORDER = {
    "clean_control": 0,
    "negation_conflict": 1,
    "multi_intent": 2,
    "out_of_scope": 3,
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def primary_intent(row: dict[str, Any]) -> str:
    return str(row.get("legacy_source", {}).get("legacy_primary_intent", ""))


def select_queries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[primary_intent(row)].append(row)

    selected: list[dict[str, Any]] = []
    used_source_groups: set[str] = set()
    for intent, quota in INTENT_QUOTAS.items():
        def specificity_rank(row: dict[str, Any]) -> int:
            if intent != "trapped_or_entrapment":
                return 0
            text = str(row.get("text", ""))
            cues = ("废墟", "墙", "掉东西", "地震", "余震", "洪水", "烟", "火")
            return 0 if any(cue in text for cue in cues) else 1

        candidates = sorted(
            grouped.get(intent, []),
            key=lambda row: (
                specificity_rank(row),
                QUERY_TYPE_ORDER.get(str(row.get("query_type", "")), 99),
                str(row.get("source_group_id", "")),
                str(row.get("query_id", "")),
            ),
        )
        intent_selected: list[dict[str, Any]] = []
        for row in candidates:
            source_group = str(row["source_group_id"])
            if source_group in used_source_groups:
                continue
            intent_selected.append(row)
            used_source_groups.add(source_group)
            if len(intent_selected) == quota:
                break
        if len(intent_selected) < quota:
            raise ValueError(
                f"cannot satisfy quota for {intent}: "
                f"{len(intent_selected)}/{quota}"
            )
        selected.extend(intent_selected)
    if len(selected) != sum(INTENT_QUOTAS.values()):
        raise AssertionError("selected query count does not match quotas")
    return selected


def candidate_evidence(
    query: dict[str, Any],
    *,
    index: BM25Index,
    chunk_rows: dict[str, dict[str, Any]],
    top_k: int,
) -> list[dict[str, Any]]:
    intent = primary_intent(query)
    allowed_hazards = INTENT_HAZARDS[intent]
    if not allowed_hazards:
        return []
    retrieval_hint = INTENT_RETRIEVAL_HINTS[intent]
    query_text = str(query["text"])
    if intent == "trapped_or_entrapment":
        if any(
            cue in query_text
            for cue in ("废墟", "墙", "裂", "晃", "地震", "余震", "倒塌")
        ):
            retrieval_hint = (
                "地震 倒塌 被埋 被困 有规律敲击 保存体力 等待救援"
            )
        elif any(cue in query_text for cue in ("火", "烟", "楼顶", "房门")):
            retrieval_hint = "火灾 被困 报警 封堵门缝 等待救援"
        else:
            retrieval_hint = (
                "被埋 被困 有规律敲击 保存体力 节约饮水 等待救援"
            )
    retrieval_text = f"{query_text} {retrieval_hint}".strip()
    ranked = index.search(retrieval_text, top_k=len(chunk_rows))
    filtered: list[dict[str, Any]] = []
    for item in ranked:
        row = chunk_rows[item.chunk.evidence_id]
        if not allowed_hazards.intersection(row.get("hazard_types", [])):
            continue
        if item.score <= 0:
            continue
        filtered.append(
            {
                "evidence_id": item.chunk.evidence_id,
                "score": round(float(item.score), 8),
                "source_id": row["source_id"],
                "parent_source_id": row["parent_source_id"],
                "source_locator": row["source_locator"],
                "title": row["title"],
                "text_preview": str(row["text"])[:180],
            }
        )
        if len(filtered) == top_k:
            break
    return filtered


def write_review_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "query_id",
        "query_text",
        "legacy_primary_intent",
        "query_type",
        "risk_level_candidate",
        "should_fallback_candidate",
        "machine_candidate_evidence_ids",
        "machine_top_score",
        "evidence_gap_flag",
        "reviewer_A_accepted_evidence_ids",
        "reviewer_A_required_actions",
        "reviewer_A_prohibited_actions",
        "reviewer_A_L0_L3",
        "reviewer_A_should_fallback",
        "reviewer_A_notes",
        "reviewer_B_accepted_evidence_ids",
        "reviewer_B_required_actions",
        "reviewer_B_prohibited_actions",
        "reviewer_B_L0_L3",
        "reviewer_B_should_fallback",
        "reviewer_B_notes",
        "adjudicated_evidence_ids",
        "adjudicated_required_actions",
        "adjudicated_prohibited_actions",
        "adjudicated_L0_L3",
        "adjudicated_should_fallback",
        "adjudicator",
        "final_status",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            candidates = row["machine_candidate_evidence"]
            writer.writerow(
                {
                    "query_id": row["query_id"],
                    "query_text": row["text"],
                    "legacy_primary_intent": row["legacy_primary_intent"],
                    "query_type": row["query_type"],
                    "risk_level_candidate": row["risk_level"],
                    "should_fallback_candidate": row["should_fallback"],
                    "machine_candidate_evidence_ids": "|".join(
                        item["evidence_id"] for item in candidates
                    ),
                    "machine_top_score": (
                        candidates[0]["score"] if candidates else ""
                    ),
                    "evidence_gap_flag": row["evidence_gap_flag"],
                    "final_status": "pending_double_review",
                }
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="选择24条先导查询并生成非金标准机器证据建议。"
    )
    parser.add_argument("--queries", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--review-csv", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--top-k", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    query_path = Path(args.queries).resolve()
    chunk_path = Path(args.chunks).resolve()
    output_path = Path(args.output).resolve()
    review_csv_path = Path(args.review_csv).resolve()
    report_path = Path(args.report).resolve()

    queries = read_jsonl(query_path)
    selected = select_queries(queries)
    raw_chunk_rows = read_jsonl(chunk_path)
    if any(row.get("status") != "draft" for row in raw_chunk_rows):
        raise ValueError("pilot evidence suggestions expect draft candidate chunks")
    chunks = [ProtocolChunk.from_dict(row) for row in raw_chunk_rows]
    index = BM25Index(chunks)
    chunk_rows = {str(row["evidence_id"]): row for row in raw_chunk_rows}

    output_rows: list[dict[str, Any]] = []
    for query in selected:
        evidence = candidate_evidence(
            query,
            index=index,
            chunk_rows=chunk_rows,
            top_k=args.top_k,
        )
        intent = primary_intent(query)
        expected_gap_control = intent == "out_of_scope"
        output_rows.append(
            {
                **query,
                "legacy_primary_intent": intent,
                "pilot_subset": "evidence_binding_24_v0.1",
                "evidence_binding_status": (
                    "machine_suggestion_pending_double_review"
                ),
                "formal_training_eligible": False,
                "gold_evidence_ids": [],
                "required_actions": [],
                "prohibited_actions": [],
                "split": "",
                "machine_candidate_evidence": evidence,
                "evidence_gap_flag": not evidence,
                "expected_gap_control": expected_gap_control,
            }
        )

    write_jsonl(output_path, output_rows)
    write_review_csv(review_csv_path, output_rows)
    report = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "formal_training_eligible": False,
        "purpose": "pilot_machine_evidence_suggestions_for_double_review",
        "inputs": {
            "queries": str(query_path),
            "queries_sha256": sha256_file(query_path),
            "chunks": str(chunk_path),
            "chunks_sha256": sha256_file(chunk_path),
        },
        "outputs": {
            "jsonl": str(output_path),
            "jsonl_sha256": sha256_file(output_path),
            "review_csv": str(review_csv_path),
            "review_csv_sha256": sha256_file(review_csv_path),
        },
        "rows": len(output_rows),
        "intent_quotas": INTENT_QUOTAS,
        "query_type_distribution": dict(
            Counter(str(row["query_type"]) for row in output_rows)
        ),
        "evidence_gap_rows": [
            row["query_id"] for row in output_rows if row["evidence_gap_flag"]
        ],
        "unexpected_evidence_gap_rows": [
            row["query_id"]
            for row in output_rows
            if row["evidence_gap_flag"] and not row["expected_gap_control"]
        ],
        "policy": {
            "machine_suggestions_are_gold": False,
            "double_review_required": True,
            "test_split_assignment_allowed": False,
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "rows": len(output_rows),
                "evidence_gaps": len(report["evidence_gap_rows"]),
                "unexpected_evidence_gaps": len(
                    report["unexpected_evidence_gap_rows"]
                ),
                "output": str(output_path),
                "review_csv": str(review_csv_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
