from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

LABEL_FIELDS = (
    "trigger_negated", "trigger_forbidden", "dangerous_action",
    "missing_action_vector", "protocol_correct", "evidence_relevant",
    "constraint_preserved", "actionable", "error_severity", "y_trigger",
    "y_miss", "y_quality", "severe_failure", "action_completeness",
    "evidence_correct", "fallback_correct", "protocol_conflict", "scope_violation",
)
DECISIONS = {"A", "B", "NEW", "UNRESOLVED", "EXCLUDE"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def check_label(labels: Any, item: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(labels, dict) or set(labels) != set(LABEL_FIELDS):
        return [f"{item}:final_value_must_contain_exactly_18_label_fields"]
    bool_fields = set(LABEL_FIELDS) - {
        "missing_action_vector", "error_severity", "action_completeness",
        "evidence_correct", "fallback_correct",
    }
    for field in bool_fields:
        if not isinstance(labels[field], bool):
            errors.append(f"{item}:{field}_must_be_boolean")
    for field in ("evidence_correct", "fallback_correct"):
        if labels[field] is not None and not isinstance(labels[field], bool):
            errors.append(f"{item}:{field}_must_be_boolean_or_null")
    missing = labels["missing_action_vector"]
    if not isinstance(missing, list) or any(not isinstance(v, str) or not v.strip() for v in missing):
        errors.append(f"{item}:missing_action_vector_invalid")
    severity = labels["error_severity"]
    if not isinstance(severity, int) or isinstance(severity, bool) or not 0 <= severity <= 4:
        errors.append(f"{item}:error_severity_invalid")
    completeness = labels["action_completeness"]
    if completeness is not None and (
        not isinstance(completeness, (int, float)) or isinstance(completeness, bool)
        or not 0 <= float(completeness) <= 1
    ):
        errors.append(f"{item}:action_completeness_invalid")
    if labels["y_trigger"] != (labels["trigger_negated"] or labels["trigger_forbidden"] or labels["dangerous_action"]):
        errors.append(f"{item}:y_trigger_not_derived")
    if labels["y_miss"] != bool(missing):
        errors.append(f"{item}:y_miss_not_derived")
    expected_quality = (
        labels["protocol_correct"] and labels["evidence_relevant"]
        and labels["constraint_preserved"] and labels["actionable"]
        and not labels["dangerous_action"]
    )
    if labels["y_quality"] != expected_quality:
        errors.append(f"{item}:y_quality_not_derived")
    if severity == 4 and not labels["severe_failure"]:
        errors.append(f"{item}:severity_4_requires_severe_failure")
    return errors


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description="验收 E1 C 全量仲裁修正版")
    parser.add_argument("--disagreements", required=True, type=Path)
    parser.add_argument("--adjudication", required=True, type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--audit-output", required=True, type=Path)
    args = parser.parse_args()
    if args.audit_output.exists():
        raise FileExistsError(f"refusing to overwrite audit: {args.audit_output}")

    disagreements = read_jsonl(args.disagreements)
    adjudication = read_jsonl(args.adjudication)
    candidates = read_jsonl(args.candidates)
    audit_rows = read_jsonl(args.audit)
    expected = [str(row.get("blind_item_id", "")) for row in disagreements]
    returned = [str(row.get("blind_item_id", "")) for row in adjudication]
    errors: list[str] = []
    if len(expected) != 313 or len(set(expected)) != 313 or "" in expected:
        errors.append("disagreement_set_not_exactly_313_unique_items")
    if len(returned) != 313 or len(set(returned)) != 313 or "" in returned:
        errors.append("adjudication_not_exactly_313_unique_items")
    if set(expected) != set(returned):
        errors.append("adjudication_blind_item_set_mismatch")
    for row in adjudication:
        item = str(row.get("blind_item_id", ""))
        disputed = row.get("disputed_fields")
        if not isinstance(disputed, list) or len(disputed) != len(set(disputed)):
            errors.append(f"{item}:disputed_fields_must_be_unique_list")
        if isinstance(disputed, list) and any(field not in LABEL_FIELDS for field in disputed):
            errors.append(f"{item}:unknown_disputed_field")
        final_value = row.get("final_value")
        if isinstance(disputed, list) and isinstance(final_value, dict) and not set(disputed) <= set(final_value):
            errors.append(f"{item}:final_value_does_not_cover_all_disputed_fields")
        errors.extend(check_label(final_value, item))
        if row.get("decision") not in DECISIONS:
            errors.append(f"{item}:invalid_decision")
        if row.get("adjudicator_id") != "ANN-C-ORG":
            errors.append(f"{item}:adjudicator_id_must_be_ANN-C-ORG")
        if not isinstance(row.get("adjudicated_at"), str) or not row["adjudicated_at"].strip():
            errors.append(f"{item}:adjudicated_at_required")

    candidate_ids = {str(row.get("blind_item_id", "")) for row in candidates}
    audit_ids = {str(row.get("blind_item_id", "")) for row in audit_rows}
    required_audits = max(1, math.ceil(len(candidate_ids) * 0.10))
    if len(audit_rows) < required_audits:
        errors.append("low_risk_audit_below_10_percent")
    if not audit_ids <= candidate_ids:
        errors.append("low_risk_audit_contains_unknown_candidate")
    for row in audit_rows:
        result = row.get("audit_result", row.get("audit_outcome"))
        if result != "CONFIRMED_LOW_RISK":
            errors.append(f"{row.get('blind_item_id')}:low_risk_audit_not_confirmed")
        if row.get("adjudicator_id") != "ANN-C-ORG":
            errors.append(f"{row.get('blind_item_id')}:audit_adjudicator_id_mismatch")

    result = {
        "schema_version": "e1-c-adjudication-repaired-audit-v1.0",
        "adjudication": {"path": str(args.adjudication), "sha256": sha256(args.adjudication), "rows": len(adjudication)},
        "disagreements": {"path": str(args.disagreements), "sha256": sha256(args.disagreements), "rows": len(disagreements)},
        "low_risk_candidates": len(candidate_ids),
        "low_risk_audit_rows": len(audit_rows),
        "required_low_risk_audit_rows": required_audits,
        "errors": errors,
        "passed": not errors,
    }
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
