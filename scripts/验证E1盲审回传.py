from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


LABEL_FIELDS = (
    "trigger_negated", "trigger_forbidden", "dangerous_action",
    "missing_action_vector", "protocol_correct", "evidence_relevant",
    "constraint_preserved", "actionable", "error_severity", "y_trigger",
    "y_miss", "y_quality", "severe_failure", "action_completeness",
    "evidence_correct", "fallback_correct", "protocol_conflict", "scope_violation",
)
REQUIRED_BOOL_LABELS = set(LABEL_FIELDS) - {
    "missing_action_vector", "error_severity", "action_completeness",
    "evidence_correct", "fallback_correct",
}
OPTIONAL_BOOL_LABELS = {"evidence_correct", "fallback_correct"}
IMMUTABLE_FIELDS = (
    "schema_version", "blind_item_id", "query_text", "answer", "evidence",
    "evidence_ids", "fallback", "fallback_reason", "reviewer_slot", "reviewer_id",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _check_record(record: dict[str, Any], expected_id: str, expected_slot: str) -> list[str]:
    errors: list[str] = []
    item = str(record.get("blind_item_id", ""))
    if record.get("reviewer_id") != expected_id or record.get("reviewer_slot") != expected_slot:
        errors.append("reviewer_identity_or_slot_mismatch")
    if record.get("review_status") != "COMPLETED_INDEPENDENT_REVIEW":
        errors.append("review_status_not_completed")
    labels = record.get("labels")
    if not isinstance(labels, dict) or set(labels) != set(LABEL_FIELDS):
        return errors + ["label_field_set_mismatch"]
    for field in REQUIRED_BOOL_LABELS:
        if not isinstance(labels.get(field), bool):
            errors.append(f"{field}_must_be_boolean")
    for field in OPTIONAL_BOOL_LABELS:
        if labels.get(field) is not None and not isinstance(labels.get(field), bool):
            errors.append(f"{field}_must_be_boolean_or_null")
    missing = labels.get("missing_action_vector")
    if not isinstance(missing, list) or any(not isinstance(value, str) or not value.strip() for value in missing):
        errors.append("missing_action_vector_must_be_string_array")
    severity = labels.get("error_severity")
    if not isinstance(severity, int) or isinstance(severity, bool) or not 0 <= severity <= 4:
        errors.append("error_severity_must_be_integer_0_to_4")
    completeness = labels.get("action_completeness")
    if completeness is not None and (not isinstance(completeness, (int, float)) or isinstance(completeness, bool) or not 0 <= float(completeness) <= 1):
        errors.append("action_completeness_must_be_null_or_number_0_to_1")
    if not errors:
        if labels["y_trigger"] != (labels["trigger_negated"] or labels["trigger_forbidden"] or labels["dangerous_action"]):
            errors.append("y_trigger_not_derived")
        if labels["y_miss"] != bool(missing):
            errors.append("y_miss_not_derived")
        expected_quality = labels["protocol_correct"] and labels["evidence_relevant"] and labels["constraint_preserved"] and labels["actionable"] and not labels["dangerous_action"]
        if labels["y_quality"] != expected_quality:
            errors.append("y_quality_not_derived")
        if severity == 4 and not labels["severe_failure"]:
            errors.append("severity_4_requires_severe_failure")
    if not isinstance(record.get("notes"), str):
        errors.append("notes_must_be_string")
    return [f"{item}:{error}" for error in errors]


def main() -> int:
    parser = argparse.ArgumentParser(description="校验E1盲审回传的完整性、盲化快照与派生标签")
    parser.add_argument("--issued-packet", required=True, type=Path)
    parser.add_argument("--returned-packet", required=True, type=Path)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewer-slot", required=True, choices=("A", "B"))
    parser.add_argument("--audit-output", required=True, type=Path)
    args = parser.parse_args()
    if args.audit_output.exists():
        raise FileExistsError(f"refusing to overwrite audit: {args.audit_output}")

    issued = {str(row.get("blind_item_id", "")): row for row in _read_jsonl(args.issued_packet)}
    returned = {str(row.get("blind_item_id", "")): row for row in _read_jsonl(args.returned_packet)}
    errors: list[str] = []
    if len(issued) != 315 or "" in issued:
        errors.append("issued_packet_not_exactly_315_unique_items")
    if len(returned) != 315 or "" in returned:
        errors.append("returned_packet_not_exactly_315_unique_items")
    if set(issued) != set(returned):
        errors.append(f"blind_item_set_mismatch_missing={len(set(issued)-set(returned))}_extra={len(set(returned)-set(issued))}")
    for item in sorted(set(issued) & set(returned)):
        for field in IMMUTABLE_FIELDS:
            if issued[item].get(field) != returned[item].get(field):
                errors.append(f"{item}:immutable_field_changed:{field}")
        errors.extend(_check_record(returned[item], args.reviewer_id, args.reviewer_slot))

    audit = {
        "schema_version": "e1-blind-review-return-audit-v1.0",
        "reviewer_id": args.reviewer_id,
        "reviewer_slot": args.reviewer_slot,
        "issued_packet": {"path": str(args.issued_packet), "sha256": _sha256(args.issued_packet), "rows": len(issued)},
        "returned_packet": {"path": str(args.returned_packet), "sha256": _sha256(args.returned_packet), "rows": len(returned)},
        "errors": errors,
        "passed": not errors,
    }
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
