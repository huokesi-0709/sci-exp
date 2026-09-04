from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import random
from pathlib import Path
from typing import Any


LABEL_FIELDS = (
    "trigger_negated",
    "trigger_forbidden",
    "dangerous_action",
    "missing_action_vector",
    "protocol_correct",
    "evidence_relevant",
    "constraint_preserved",
    "actionable",
    "error_severity",
    "y_trigger",
    "y_miss",
    "y_quality",
    "severe_failure",
    "action_completeness",
    "evidence_correct",
    "fallback_correct",
    "protocol_conflict",
    "scope_violation",
)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl_new(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite blind-review asset: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def _blind_id(secret: bytes, run_key: str) -> str:
    digest = hmac.new(secret, run_key.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"E1-BLIND-{digest[:20].upper()}"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _validate_reviewer_ids(
    reviewer_a_id: str,
    reviewer_b_id: str,
    adjudicator_id: str,
) -> tuple[str, str, str]:
    identities = tuple(
        value.strip() for value in (reviewer_a_id, reviewer_b_id, adjudicator_id)
    )
    if any(not value for value in identities):
        raise ValueError("reviewer A, reviewer B and adjudicator IDs are required")
    if len(set(identities)) != 3:
        raise ValueError("reviewer A, reviewer B and adjudicator IDs must be distinct")
    return identities


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从315条有效E1 merged结果生成配置盲法A/B审查包和主持人私有交叉表"
    )
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--runs", required=True, action="append")
    parser.add_argument("--blind-salt-file", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--reviewer-a-id", required=True)
    parser.add_argument("--reviewer-b-id", required=True)
    parser.add_argument("--adjudicator-id", required=True)
    parser.add_argument("--review-seed", type=int, default=20260831)
    args = parser.parse_args()
    reviewer_a_id, reviewer_b_id, adjudicator_id = _validate_reviewer_ids(
        args.reviewer_a_id,
        args.reviewer_b_id,
        args.adjudicator_id,
    )

    manifest = _read_jsonl(Path(args.manifest))
    queries = {
        str(row["query_id"]): row
        for row in _read_jsonl(Path(args.queries))
    }
    runs: list[dict[str, Any]] = []
    for value in args.runs:
        runs.extend(_read_jsonl(Path(value)))

    if len(manifest) != 315:
        raise ValueError(f"manifest must contain 315 rows, got {len(manifest)}")
    by_run_key = {str(row.get("run_key", "")): row for row in runs}
    if len(by_run_key) != len(runs):
        raise ValueError("run files contain duplicate or empty run_key values")
    expected_keys = [str(row["run_key"]) for row in manifest]
    missing = [key for key in expected_keys if key not in by_run_key]
    extra = sorted(set(by_run_key) - set(expected_keys))
    if missing or extra:
        raise ValueError(
            f"run/manifest mismatch: missing={len(missing)}, extra={len(extra)}"
        )

    invalid: list[str] = []
    for key in expected_keys:
        row = by_run_key[key]
        telemetry = row.get("telemetry") or {}
        if row.get("status") != "ok" or telemetry.get("external_meter_valid") is not True:
            invalid.append(key)
    if invalid:
        raise ValueError(
            f"blind packets require 315 successful physically valid outputs; invalid={len(invalid)}"
        )

    secret = Path(args.blind_salt_file).read_bytes().strip()
    if len(secret) < 32:
        raise ValueError("blind salt must contain at least 32 bytes and stay outside Git")

    review_rows: list[dict[str, Any]] = []
    crosswalk: list[dict[str, Any]] = []
    adjudication: list[dict[str, Any]] = []
    for task in manifest:
        run_key = str(task["run_key"])
        run = by_run_key[run_key]
        query_id = str(task["query_id"])
        blind_item_id = _blind_id(secret, run_key)
        answer = str(run.get("answer", ""))
        review_rows.append(
            {
                "schema_version": "e1-blind-review-item-v1.0",
                "blind_item_id": blind_item_id,
                "query_text": str(queries[query_id]["text"]),
                "answer": answer,
                "evidence": run.get("evidence", []),
                "evidence_ids": run.get("evidence_ids", []),
                "fallback": bool(run.get("fallback", False)),
                "fallback_reason": run.get("fallback_reason"),
                "reviewer_id": "",
                "labels": {field: None for field in LABEL_FIELDS},
                "notes": "",
                "review_status": "PENDING_INDEPENDENT_REVIEW",
            }
        )
        crosswalk.append(
            {
                "blind_item_id": blind_item_id,
                "run_order": int(task["run_order"]),
                "run_key": run_key,
                "query_id": query_id,
                "configuration": str(task["configuration"]),
                "repetition": int(task["repetition"]),
                "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest().upper(),
            }
        )
        adjudication.append(
            {
                "label_schema_version": "input-config-outcome-v2.0",
                "blind_item_id": blind_item_id,
                "query_id": query_id,
                "configuration": str(task["configuration"]),
                "repetition": int(task["repetition"]),
                **{field: None for field in LABEL_FIELDS},
                "reviewer_A_record": "",
                "reviewer_B_record": "",
                "adjudication_reason": "",
                "notes": "",
                "adjudicator_id": adjudicator_id,
                "adjudication_status": "PENDING_AFTER_A_B_REVIEW",
            }
        )

    # A/B see the same 315 blinded records, but in independently randomized
    # deterministic orders.  Sharing an order makes it unnecessarily easy to
    # coordinate progress item-by-item, which weakens independent review.
    reviewer_a_rows = list(review_rows)
    reviewer_b_rows = list(review_rows)
    random.Random(args.review_seed).shuffle(reviewer_a_rows)
    random.Random(args.review_seed + 1).shuffle(reviewer_b_rows)
    output = Path(args.output_directory)
    reviewer_a_path = output / "reviewer_A" / "E1_review_A.jsonl"
    reviewer_b_path = output / "reviewer_B" / "E1_review_B.jsonl"
    crosswalk_path = output / "host_private" / "E1_blind_crosswalk.jsonl"
    adjudication_path = output / "host_private" / "E1_adjudication_template.jsonl"
    summary_path = output / "E1_blind_review_package_summary.json"
    expected_outputs = (
        reviewer_a_path,
        reviewer_b_path,
        crosswalk_path,
        adjudication_path,
        summary_path,
    )
    existing_outputs = [path for path in expected_outputs if path.exists()]
    if existing_outputs:
        raise FileExistsError(
            "refusing to create a partial/overwriting blind-review package: "
            + ", ".join(str(path) for path in existing_outputs)
        )

    reviewer_a = [
        dict(row, reviewer_slot="A", reviewer_id=reviewer_a_id)
        for row in reviewer_a_rows
    ]
    reviewer_b = [
        dict(row, reviewer_slot="B", reviewer_id=reviewer_b_id)
        for row in reviewer_b_rows
    ]
    _write_jsonl_new(reviewer_a_path, reviewer_a)
    _write_jsonl_new(reviewer_b_path, reviewer_b)
    _write_jsonl_new(crosswalk_path, crosswalk)
    _write_jsonl_new(
        adjudication_path,
        adjudication,
    )
    summary = {
        "schema_version": "e1-blind-review-package-v1.0",
        "items": len(review_rows),
        "reviewer_a_order_seed": args.review_seed,
        "reviewer_b_order_seed": args.review_seed + 1,
        "reviewer_orders_are_independently_randomized": True,
        "reviewer_a_id": reviewer_a_id,
        "reviewer_b_id": reviewer_b_id,
        "adjudicator_id": adjudicator_id,
        "configuration_hidden_from_review_packets": True,
        "crosswalk_visibility": "HOST_ONLY_UNTIL_ADJUDICATION_IS_LOCKED",
        "issued_packets": {
            "reviewer_A": {
                "path": str(reviewer_a_path),
                "rows": len(reviewer_a),
                "sha256": _sha256(reviewer_a_path),
            },
            "reviewer_B": {
                "path": str(reviewer_b_path),
                "rows": len(reviewer_b),
                "sha256": _sha256(reviewer_b_path),
            },
        },
        "formal_completion_rule": "315 A reviews + 315 B reviews + all disagreements adjudicated",
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
