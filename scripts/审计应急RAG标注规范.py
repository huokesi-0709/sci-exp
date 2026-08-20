from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FORMAL_STATUS = {"draft", "double_reviewed", "adjudicated", "quality_checked", "frozen"}
DISASTER_LABELS = {"地震", "洪水", "火灾", "极端低温", "综合/不明", "域外"}
QUERY_LABELS = {
    "出血/休克",
    "创伤/骨折",
    "头部或意识",
    "呼吸困难",
    "低温",
    "被困",
    "余震/坍塌",
    "挤压",
    "缺水",
    "心理支持",
    "低电量",
    "域外",
    "综合/不明",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def risk_number(value: Any) -> int | None:
    if isinstance(value, str) and value.upper() in {"L0", "L1", "L2", "L3"}:
        return int(value[1])
    if isinstance(value, int) and not isinstance(value, bool) and value in range(4):
        return value
    return None


def audit_rows(
    rows: list[dict[str, Any]],
    *,
    evidence_ids: set[str],
    name: str,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    counts = Counter()
    for index, row in enumerate(rows, start=1):
        query_id = str(row.get("query_id", ""))
        counts["rows"] += 1
        for field in (
            "query_id",
            "text",
            "language",
            "disaster_type",
            "query_type",
            "source_group_id",
            "gold_evidence_ids",
            "required_actions",
            "prohibited_actions",
        ):
            if field not in row:
                errors.append({"row": index, "query_id": query_id, "code": f"missing:{field}"})
        if risk_number(row.get("risk_level")) is None:
            errors.append({"row": index, "query_id": query_id, "code": "invalid:risk_level"})
        if row.get("disaster_type_label") not in DISASTER_LABELS:
            errors.append(
                {"row": index, "query_id": query_id, "code": "invalid:disaster_type_label"}
            )
        if row.get("query_type_label") not in QUERY_LABELS:
            errors.append(
                {"row": index, "query_id": query_id, "code": "invalid:query_type_label"}
            )
        if not isinstance(row.get("should_fallback"), bool):
            errors.append({"row": index, "query_id": query_id, "code": "invalid:should_fallback"})
        for field in ("gold_evidence_ids", "required_actions", "prohibited_actions"):
            value = row.get(field)
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                errors.append({"row": index, "query_id": query_id, "code": f"invalid:{field}"})
        if isinstance(row.get("gold_evidence_ids"), list):
            missing = sorted(set(row["gold_evidence_ids"]) - evidence_ids)
            if missing:
                errors.append(
                    {
                        "row": index,
                        "query_id": query_id,
                        "code": "missing:evidence_id",
                        "values": missing,
                    }
                )
            if not row["gold_evidence_ids"] and row.get("evidence_gap_flag") is not True:
                errors.append(
                    {"row": index, "query_id": query_id, "code": "empty_evidence_without_gap"}
                )
        overlap = set(row.get("required_actions", [])) & set(
            row.get("prohibited_actions", [])
        )
        if overlap:
            errors.append(
                {
                    "row": index,
                    "query_id": query_id,
                    "code": "required_prohibited_conflict",
                    "values": sorted(overlap),
                }
            )
        status = row.get("annotation_status")
        if status is not None and status not in FORMAL_STATUS:
            errors.append(
                {"row": index, "query_id": query_id, "code": "invalid:annotation_status"}
            )
        if row.get("data_status") == "development_gold":
            if row.get("formal_training_eligible") is not False:
                errors.append(
                    {"row": index, "query_id": query_id, "code": "development_gold_training_eligible"}
                )
            if row.get("final_evaluation_eligible") is not False:
                errors.append(
                    {"row": index, "query_id": query_id, "code": "development_gold_final_eligible"}
                )
            if row.get("split_scope") != "development":
                errors.append(
                    {"row": index, "query_id": query_id, "code": "development_gold_wrong_split_scope"}
                )
        for key in ("reviewer_A", "reviewer_B"):
            reviewer = row.get(key)
            if reviewer is not None and not isinstance(reviewer, dict):
                errors.append(
                    {"row": index, "query_id": query_id, "code": f"invalid:{key}"}
                )
        counts[f"risk_{risk_number(row.get('risk_level'))}"] += 1
        counts[f"fallback_{str(row.get('should_fallback')).lower()}"] += 1
        counts[f"status_{status or 'missing'}"] += 1
    return {"name": name, "counts": dict(counts), "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description="审计离线应急 RAG v1.0 标注规范")
    parser.add_argument(
        "--input",
        action="append",
        type=Path,
        help="待审 JSONL，可重复指定；默认审计正式400开发gold和两份仲裁结果",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    protocol_path = DATA / "processed" / "protocols.jsonl"
    protocol_rows = read_jsonl(protocol_path)
    evidence_ids = {str(row["evidence_id"]) for row in protocol_rows}
    inputs = args.input or [
        DATA / "processed" / "正式400条分层冻结_v2.0.jsonl",
        DATA / "annotations" / "正式96条仲裁结果_v1.0.jsonl",
        DATA / "annotations" / "新增304条仲裁结果_v1.0.jsonl",
    ]
    reports = [
        audit_rows(read_jsonl(path), evidence_ids=evidence_ids, name=str(path.relative_to(ROOT)))
        for path in inputs
    ]
    result = {
        "report_version": "annotation-standard-audit-v1.0",
        "specification": "应急RAG数据标注规范_v1.0",
        "protocol_count": len(protocol_rows),
        "inputs": reports,
        "output_level": {
            "status": "blocked_pending_formal_runtime",
            "template": "data/annotations/adjudication_template.jsonl",
            "records_found": 0,
            "reason": (
                "formal runtime gate is not passed; do not fabricate "
                "query_id+configuration+repetition labels"
            ),
        },
        "error_count": sum(len(report["errors"]) for report in reports),
        "quality_gates": {
            "query_fields_and_types": all(
                not any(error["code"].startswith(("missing:", "invalid:")) for error in report["errors"])
                for report in reports
            ),
            "evidence_ids_traceable": all(
                not any(error["code"] == "missing:evidence_id" for error in report["errors"])
                for report in reports
            ),
            "no_required_prohibited_conflict": all(
                not any(error["code"] == "required_prohibited_conflict" for error in report["errors"])
                for report in reports
            ),
            "development_gold_blocked_from_final_use": all(
                not any(
                error["code"]
                    in {
                        "development_gold_training_eligible",
                        "development_gold_final_eligible",
                        "development_gold_wrong_split_scope",
                    }
                    for error in report["errors"]
                )
                for report in reports
            ),
        },
    }
    result["all_quality_gates_pass"] = all(result["quality_gates"].values())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["all_quality_gates_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
