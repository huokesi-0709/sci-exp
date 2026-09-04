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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser(description="使用 Git 外私有 crosswalk 合并 E1 C 最终标签")
    parser.add_argument("--master", required=True, type=Path)
    parser.add_argument("--crosswalk", required=True, type=Path)
    parser.add_argument("--adjudication", required=True, type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--reviewer-a", required=True, type=Path)
    parser.add_argument("--reviewer-b", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit-output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.audit_output.exists():
        raise FileExistsError("refusing to overwrite final merge outputs")

    master = read_jsonl(args.master)
    crosswalk = read_jsonl(args.crosswalk)
    adjudication = read_jsonl(args.adjudication)
    candidates = read_jsonl(args.candidates)
    audits = read_jsonl(args.audit)
    reviewer_a = {str(r["blind_item_id"]): r for r in read_jsonl(args.reviewer_a)}
    reviewer_b = {str(r["blind_item_id"]): r for r in read_jsonl(args.reviewer_b)}

    errors: list[str] = []
    if len(master) != 315 or len({str(r.get("run_key")) for r in master}) != 315:
        errors.append("master_must_be_315_unique_run_keys")
    if len(crosswalk) != 315 or len({str(r.get("blind_item_id")) for r in crosswalk}) != 315:
        errors.append("crosswalk_must_be_315_unique_blind_ids")
    c_map = {str(r.get("blind_item_id")): r for r in adjudication}
    candidate_map = {str(r.get("blind_item_id")): r for r in candidates}
    audit_map = {str(r.get("blind_item_id")): r for r in audits}
    if len(c_map) != 313:
        errors.append("c_adjudication_must_have_313_unique_rows")
    if not set(c_map) <= {str(r.get("blind_item_id")) for r in crosswalk}:
        errors.append("c_ids_not_in_crosswalk")
    candidate_ids = set(candidate_map)
    if len(candidate_ids) != 2 or not candidate_ids <= set(audit_map):
        errors.append("two_low_risk_candidates_must_be_audited")
    for item in candidate_ids:
        if audit_map[item].get("audit_result", audit_map[item].get("audit_outcome")) != "CONFIRMED_LOW_RISK":
            errors.append(f"{item}:low_risk_audit_not_confirmed")
        if reviewer_a.get(item, {}).get("labels") != reviewer_b.get(item, {}).get("labels"):
            errors.append(f"{item}:A_B_candidate_labels_not_identical")

    merged: list[dict[str, Any]] = []
    used: set[str] = set()
    for link in crosswalk:
        blind = str(link.get("blind_item_id"))
        if blind in c_map:
            row = c_map[blind]
            labels = row.get("final_value")
            meta = {
                "source": "ANN-C-ORG",
                "decision": row.get("decision"),
                "supporting_evidence_ids": row.get("supporting_evidence_ids"),
                "adjudication_reason": row.get("adjudication_reason"),
                "adjudicator_id": row.get("adjudicator_id"),
                "adjudicated_at": row.get("adjudicated_at"),
            }
        elif blind in candidate_map:
            labels = candidate_map[blind].get("labels")
            meta = {
                "source": "A_B_AGREEMENT_AUDITED_BY_ANN-C-ORG",
                "decision": "AGREEMENT_AUDITED",
                "supporting_evidence_ids": reviewer_a.get(blind, {}).get("evidence_ids", []),
                "adjudication_reason": audit_map[blind].get("audit_note", "A/B exact agreement; low-risk audit confirmed."),
                "adjudicator_id": audit_map[blind].get("adjudicator_id", "ANN-C-ORG"),
                "adjudicated_at": audit_map[blind].get("adjudicated_at", audit_map[blind].get("audit_timestamp")),
            }
        else:
            errors.append(f"{blind}:no_final_label_source")
            continue
        if not isinstance(labels, dict) or set(labels) != set(LABEL_FIELDS):
            errors.append(f"{blind}:final_label_must_have_18_fields")
            continue
        run_key = str(link.get("run_key"))
        source = next((r for r in master if str(r.get("run_key")) == run_key), None)
        if source is None:
            errors.append(f"{blind}:crosswalk_run_key_missing_from_master")
            continue
        value = dict(source)
        value["blind_item_id"] = blind
        value["adjudication"] = dict(labels, **meta)
        merged.append(value)
        used.add(blind)
    if len(merged) != 315 or used != {str(r.get("blind_item_id")) for r in crosswalk}:
        errors.append("merged_output_must_have_all_315_crosswalk_items")
    if errors:
        result = {"schema_version": "e1-final-merge-audit-v1.0", "passed": False, "errors": errors}
        args.audit_output.parent.mkdir(parents=True, exist_ok=True)
        args.audit_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged), encoding="utf-8")
    result = {
        "schema_version": "e1-final-merge-audit-v1.0",
        "passed": True,
        "rows": len(merged),
        "c_adjudicated_rows": len(c_map),
        "low_risk_audited_rows": len(candidate_ids),
        "configurations": {key: sum(str(r.get("configuration")) == key for r in merged) for key in ("C0", "C1", "C2")},
        "output": {"path": str(args.output), "sha256": sha256(args.output)},
        "inputs": {
            "master_sha256": sha256(args.master),
            "crosswalk_sha256": sha256(args.crosswalk),
            "adjudication_sha256": sha256(args.adjudication),
            "candidate_sha256": sha256(args.candidates),
            "audit_sha256": sha256(args.audit),
        },
        "private_boundary": "crosswalk and reviewer packets remain outside Git",
    }
    args.audit_output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
