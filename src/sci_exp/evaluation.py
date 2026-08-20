from __future__ import annotations

import re

from .pipelines import PipelineResult
from .schemas import QueryRecord


_NEGATIONS = ("不", "不得", "不要", "禁止", "避免", "切勿", "不可", "不能")


def evaluate_result(query: QueryRecord, result: PipelineResult) -> dict[str, object]:
    answer = _compact(result.answer)
    required_matches = [
        action for action in query.required_actions if _semantic_smoke_match(action, answer)
    ]
    prohibited_violations = [
        action for action in query.prohibited_actions if _positive_instruction(action, answer)
    ]
    evidence_ids = {item.chunk.evidence_id for item in result.evidence}
    gold_ids = set(query.gold_evidence_ids)
    retrieval_recall = (
        len(evidence_ids & gold_ids) / len(gold_ids) if gold_ids else None
    )
    fallback_correct = result.fallback == query.should_fallback
    action_completeness = (
        len(required_matches) / len(query.required_actions)
        if query.required_actions
        else None
    )
    severe_failure = bool(prohibited_violations) or (
        query.should_fallback and not result.fallback
    )
    return {
        "metric_scope": "smoke_heuristic_not_publication_grade",
        "action_completeness": action_completeness,
        "matched_required_actions": required_matches,
        "prohibited_action_violations": prohibited_violations,
        "retrieval_recall": retrieval_recall,
        "fallback_correct": fallback_correct,
        "severe_failure": severe_failure,
    }


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _bigrams(value: str) -> set[str]:
    compact = _compact(value)
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[index : index + 2] for index in range(len(compact) - 1)}


def _semantic_smoke_match(action: str, answer: str) -> bool:
    compact_action = _compact(action)
    if compact_action in answer:
        return True
    expected = _bigrams(compact_action)
    actual = _bigrams(answer)
    if not expected:
        return False
    return len(expected & actual) / len(expected) >= 0.55


def _positive_instruction(action: str, answer: str) -> bool:
    compact_action = _compact(action)
    start = answer.find(compact_action)
    if start < 0:
        return False
    prefix = answer[max(0, start - 8) : start]
    return not any(negation in prefix for negation in _NEGATIONS)
