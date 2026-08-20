from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CSV_FIELDS = [
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


def join_values(values: list[str]) -> str:
    return "|".join(values)


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def cohen_kappa(left: list[Any], right: list[Any]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("kappa inputs must be non-empty and equal length")
    labels = set(left) | set(right)
    observed = sum(a == b for a, b in zip(left, right)) / len(left)
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        (left_counts[label] / len(left))
        * (right_counts[label] / len(right))
        for label in labels
    )
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def jaccard(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    return len(left_set & right_set) / len(left_set | right_set)


def validate(
    *,
    candidates: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    decision_data: dict[str, Any],
) -> None:
    candidate_ids = [str(row["query_id"]) for row in candidates]
    decision_rows = list(decision_data["decisions"])
    decision_ids = [str(row["query_id"]) for row in decision_rows]
    if len(candidate_ids) != 24 or len(set(candidate_ids)) != 24:
        raise ValueError("candidate file must contain 24 unique queries")
    if set(candidate_ids) != set(decision_ids):
        raise ValueError("decision query IDs do not match candidate IDs")
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError("duplicate query ID in decisions")

    evidence_ids = {str(row["evidence_id"]) for row in chunks}
    profiles = dict(decision_data["profiles"])
    for row in decision_rows:
        profile_name = str(row["profile"])
        if profile_name not in profiles:
            raise ValueError(f"{row['query_id']}: unknown profile")
        profile = profiles[profile_name]
        required = list(profile["required_actions"])
        prohibited = list(profile["prohibited_actions"])
        if not required or not prohibited:
            raise ValueError(
                f"{row['query_id']}: actions must not be empty"
            )
        if set(required) & set(prohibited):
            raise ValueError(
                f"{row['query_id']}: required/prohibited action conflict"
            )
        for role in ("A", "B", "final"):
            review = row[role]
            if review["risk_level"] not in {0, 1, 2, 3}:
                raise ValueError(
                    f"{row['query_id']}:{role}: invalid risk level"
                )
            if not isinstance(review["should_fallback"], bool):
                raise ValueError(
                    f"{row['query_id']}:{role}: fallback must be bool"
                )
            missing = set(review["evidence_ids"]) - evidence_ids
            if missing:
                raise ValueError(
                    f"{row['query_id']}:{role}: missing evidence {missing}"
                )
            if not str(review["notes"]).strip():
                raise ValueError(
                    f"{row['query_id']}:{role}: notes required"
                )


def build_outputs(
    *,
    candidates: list[dict[str, Any]],
    decision_data: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    decisions = {
        str(row["query_id"]): row for row in decision_data["decisions"]
    }
    profiles = dict(decision_data["profiles"])
    csv_rows: list[dict[str, Any]] = []
    adjudicated_rows: list[dict[str, Any]] = []

    for candidate in candidates:
        query_id = str(candidate["query_id"])
        decision = decisions[query_id]
        profile = profiles[str(decision["profile"])]
        required = list(profile["required_actions"])
        prohibited = list(profile["prohibited_actions"])
        review_a = decision["A"]
        review_b = decision["B"]
        final = decision["final"]
        machine_candidates = list(candidate["machine_candidate_evidence"])

        csv_rows.append(
            {
                "query_id": query_id,
                "query_text": candidate["text"],
                "legacy_primary_intent": candidate[
                    "legacy_primary_intent"
                ],
                "query_type": candidate["query_type"],
                "risk_level_candidate": candidate["risk_level"],
                "should_fallback_candidate": bool_text(
                    bool(candidate["should_fallback"])
                ),
                "machine_candidate_evidence_ids": join_values(
                    [item["evidence_id"] for item in machine_candidates]
                ),
                "machine_top_score": (
                    machine_candidates[0]["score"]
                    if machine_candidates
                    else ""
                ),
                "evidence_gap_flag": bool_text(
                    bool(candidate["evidence_gap_flag"])
                ),
                "reviewer_A_accepted_evidence_ids": join_values(
                    list(review_a["evidence_ids"])
                ),
                "reviewer_A_required_actions": join_values(required),
                "reviewer_A_prohibited_actions": join_values(prohibited),
                "reviewer_A_L0_L3": f"L{review_a['risk_level']}",
                "reviewer_A_should_fallback": bool_text(
                    review_a["should_fallback"]
                ),
                "reviewer_A_notes": review_a["notes"],
                "reviewer_B_accepted_evidence_ids": join_values(
                    list(review_b["evidence_ids"])
                ),
                "reviewer_B_required_actions": join_values(required),
                "reviewer_B_prohibited_actions": join_values(prohibited),
                "reviewer_B_L0_L3": f"L{review_b['risk_level']}",
                "reviewer_B_should_fallback": bool_text(
                    review_b["should_fallback"]
                ),
                "reviewer_B_notes": review_b["notes"],
                "adjudicated_evidence_ids": join_values(
                    list(final["evidence_ids"])
                ),
                "adjudicated_required_actions": join_values(required),
                "adjudicated_prohibited_actions": join_values(prohibited),
                "adjudicated_L0_L3": f"L{final['risk_level']}",
                "adjudicated_should_fallback": bool_text(
                    final["should_fallback"]
                ),
                "adjudicator": decision_data["reviewers"]["adjudicator"],
                "final_status": (
                    "adjudicated_pending_protocol_approval"
                ),
            }
        )

        adjudicated = dict(candidate)
        adjudicated.update(
            {
                "risk_level": int(final["risk_level"]),
                "should_fallback": bool(final["should_fallback"]),
                "gold_evidence_ids": list(final["evidence_ids"]),
                "required_actions": required,
                "prohibited_actions": prohibited,
                "annotation_status": "adjudicated",
                "annotation_version": "pilot24-v0.1",
                "evidence_binding_status": (
                    "adjudicated_pending_protocol_approval"
                ),
                "pilot_status": (
                    "adjudicated_pending_protocol_and_license_approval"
                ),
                "formal_training_eligible": False,
                "split": "",
                "review_record": {
                    "reviewer_A": review_a,
                    "reviewer_B": review_b,
                    "adjudication": final,
                    "adjudicator": decision_data["reviewers"][
                        "adjudicator"
                    ],
                    "profile": decision["profile"],
                },
            }
        )
        adjudicated_rows.append(adjudicated)
    return csv_rows, adjudicated_rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def build_report(
    *,
    candidates: list[dict[str, Any]],
    decision_data: dict[str, Any],
    adjudicated_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    decisions = list(decision_data["decisions"])
    risk_a = [row["A"]["risk_level"] for row in decisions]
    risk_b = [row["B"]["risk_level"] for row in decisions]
    fallback_a = [row["A"]["should_fallback"] for row in decisions]
    fallback_b = [row["B"]["should_fallback"] for row in decisions]
    evidence_scores = [
        jaccard(row["A"]["evidence_ids"], row["B"]["evidence_ids"])
        for row in decisions
    ]
    evidence_exact = sum(
        set(row["A"]["evidence_ids"]) == set(row["B"]["evidence_ids"])
        for row in decisions
    )
    fallback_disagreements = [
        row["query_id"]
        for row in decisions
        if row["A"]["should_fallback"] != row["B"]["should_fallback"]
    ]
    evidence_disagreements = [
        row["query_id"]
        for row in decisions
        if set(row["A"]["evidence_ids"])
        != set(row["B"]["evidence_ids"])
    ]

    machine_by_query = {
        row["query_id"]: {
            item["evidence_id"] for item in row["machine_candidate_evidence"]
        }
        for row in candidates
    }
    final_with_evidence = [
        row for row in adjudicated_rows if row["gold_evidence_ids"]
    ]
    machine_recall_values = [
        len(
            set(row["gold_evidence_ids"])
            & machine_by_query[row["query_id"]]
        )
        / len(set(row["gold_evidence_ids"]))
        for row in final_with_evidence
    ]

    return {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "pilot24_double_review_and_adjudication",
        "rows": len(decisions),
        "agreement": {
            "risk_level_exact": sum(
                left == right for left, right in zip(risk_a, risk_b)
            )
            / len(decisions),
            "risk_level_cohen_kappa": round(
                cohen_kappa(risk_a, risk_b), 6
            ),
            "fallback_exact": sum(
                left == right
                for left, right in zip(fallback_a, fallback_b)
            )
            / len(decisions),
            "fallback_cohen_kappa": round(
                cohen_kappa(fallback_a, fallback_b), 6
            ),
            "evidence_exact": evidence_exact / len(decisions),
            "evidence_mean_jaccard": round(
                sum(evidence_scores) / len(evidence_scores), 6
            ),
            "fallback_disagreement_rows": fallback_disagreements,
            "evidence_disagreement_rows": evidence_disagreements,
        },
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
            "evidence_gap_rows": [
                row["query_id"]
                for row in adjudicated_rows
                if not row["gold_evidence_ids"]
            ],
        },
        "machine_suggestion_diagnostic": {
            "adjudicated_rows_with_evidence": len(final_with_evidence),
            "mean_gold_evidence_recall_at_3": round(
                sum(machine_recall_values) / len(machine_recall_values),
                6,
            ),
            "rows_with_complete_gold_coverage": sum(
                value == 1 for value in machine_recall_values
            ),
        },
        "status": {
            "annotation_complete": True,
            "formal_training_eligible": False,
            "reason": (
                "adjudication complete; protocol content and license "
                "approval remain pending"
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="执行先导24条双轮审查决定、仲裁和一致性统计。"
    )
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--review-csv", required=True)
    parser.add_argument("--adjudicated-output", required=True)
    parser.add_argument("--report", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidates_path = Path(args.candidates).resolve()
    chunks_path = Path(args.chunks).resolve()
    decisions_path = Path(args.decisions).resolve()
    review_csv_path = Path(args.review_csv).resolve()
    adjudicated_output_path = Path(args.adjudicated_output).resolve()
    report_path = Path(args.report).resolve()

    candidates = read_jsonl(candidates_path)
    chunks = read_jsonl(chunks_path)
    decision_data = json.loads(decisions_path.read_text(encoding="utf-8"))
    validate(
        candidates=candidates,
        chunks=chunks,
        decision_data=decision_data,
    )
    csv_rows, adjudicated_rows = build_outputs(
        candidates=candidates,
        decision_data=decision_data,
    )
    write_csv(review_csv_path, csv_rows)
    write_jsonl(adjudicated_output_path, adjudicated_rows)
    report = build_report(
        candidates=candidates,
        decision_data=decision_data,
        adjudicated_rows=adjudicated_rows,
    )
    report["inputs"] = {
        "candidates_sha256": sha256_file(candidates_path),
        "chunks_sha256": sha256_file(chunks_path),
        "decisions_sha256": sha256_file(decisions_path),
    }
    report["outputs"] = {
        "review_csv_sha256": sha256_file(review_csv_path),
        "adjudicated_output_sha256": sha256_file(
            adjudicated_output_path
        ),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "rows": report["rows"],
                "agreement": report["agreement"],
                "evidence_gap_rows": report[
                    "adjudicated_distribution"
                ]["evidence_gap_rows"],
                "formal_training_eligible": False,
                "report": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
