from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable

from .schemas import ProtocolChunk, QueryRecord


ANNOTATION_STATUSES = {
    "draft",
    "double_reviewed",
    "adjudicated",
    "quality_checked",
    "frozen",
}
DEVELOPMENT_DATA_STATUS = "development_gold"


def validate_protocols(protocols: Iterable[ProtocolChunk]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, protocol in enumerate(protocols):
        prefix = f"protocol[{index}]"
        if not protocol.evidence_id:
            errors.append(f"{prefix}: empty evidence_id")
        if protocol.evidence_id in seen:
            errors.append(f"{prefix}: duplicate evidence_id={protocol.evidence_id}")
        seen.add(protocol.evidence_id)
        if not protocol.text:
            errors.append(f"{prefix}: empty text")
        if not protocol.source_org:
            errors.append(f"{prefix}: empty source_org")
        if protocol.authority_level < 0:
            errors.append(f"{prefix}: authority_level must be non-negative")
    return errors


def validate_queries(
    queries: Iterable[QueryRecord],
    evidence_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, query in enumerate(queries):
        prefix = f"query[{index}]"
        if not query.query_id:
            errors.append(f"{prefix}: empty query_id")
        if query.query_id in seen:
            errors.append(f"{prefix}: duplicate query_id={query.query_id}")
        seen.add(query.query_id)
        if not query.text:
            errors.append(f"{prefix}: empty text")
        if query.risk_level not in {0, 1, 2, 3}:
            errors.append(f"{prefix}: risk_level must be 0..3")
        if not query.source_group_id:
            errors.append(f"{prefix}: empty source_group_id")
        if evidence_ids is not None:
            missing = sorted(set(query.gold_evidence_ids) - evidence_ids)
            if missing:
                errors.append(f"{prefix}: missing gold evidence ids={missing}")
    return errors


def validate_annotation_metadata(
    rows: Iterable[dict],
    *,
    evidence_ids: set[str] | None = None,
) -> list[str]:
    """Validate the v1.0 annotation contract without inferring labels."""
    errors: list[str] = []
    for index, row in enumerate(rows):
        prefix = f"row[{index}]"
        if not row.get("query_id") or not row.get("text"):
            errors.append(f"{prefix}: query_id/text required")
        if row.get("annotation_status") not in ANNOTATION_STATUSES:
            errors.append(
                f"{prefix}: annotation_status must be one of "
                f"{sorted(ANNOTATION_STATUSES)}"
            )
        for field in ("gold_evidence_ids", "required_actions", "prohibited_actions"):
            value = row.get(field)
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                errors.append(f"{prefix}: {field} must be a list of non-empty strings")
        overlap = set(row.get("required_actions", [])) & set(
            row.get("prohibited_actions", [])
        )
        if overlap:
            errors.append(f"{prefix}: required/prohibited conflict={sorted(overlap)}")
        evidence = row.get("gold_evidence_ids", [])
        if evidence_ids is not None:
            missing = sorted(set(evidence) - evidence_ids)
            if missing:
                errors.append(f"{prefix}: missing evidence ids={missing}")
        if not evidence and row.get("evidence_gap_flag") is not True:
            errors.append(f"{prefix}: empty evidence requires evidence_gap_flag=true")
        if row.get("data_status") == DEVELOPMENT_DATA_STATUS:
            if row.get("formal_training_eligible") is not False:
                errors.append(f"{prefix}: development_gold cannot be training eligible")
            if row.get("final_evaluation_eligible") is not False:
                errors.append(f"{prefix}: development_gold cannot be final-evaluation eligible")
    return errors


def validate_no_group_leakage(queries: Iterable[QueryRecord]) -> list[str]:
    group_splits: dict[str, set[str]] = defaultdict(set)
    query_splits: dict[str, set[str]] = defaultdict(set)
    for query in queries:
        if query.split:
            group_splits[query.source_group_id].add(query.split)
            query_splits[query.query_id].add(query.split)
    errors: list[str] = []
    for group, splits in group_splits.items():
        if len(splits) > 1:
            errors.append(f"source_group_id={group} leaks across splits={sorted(splits)}")
    for query_id, splits in query_splits.items():
        if len(splits) > 1:
            errors.append(f"query_id={query_id} leaks across splits={sorted(splits)}")
    return errors


def dataset_summary(queries: Iterable[QueryRecord]) -> dict[str, object]:
    query_list = list(queries)
    return {
        "n_queries": len(query_list),
        "split": dict(Counter(query.split or "unassigned" for query in query_list)),
        "disaster_type": dict(Counter(query.disaster_type for query in query_list)),
        "query_type": dict(Counter(query.query_type for query in query_list)),
        "risk_level": dict(Counter(str(query.risk_level) for query in query_list)),
        "language": dict(Counter(query.language for query in query_list)),
        "should_fallback": dict(Counter(str(query.should_fallback) for query in query_list)),
    }
