from __future__ import annotations

import math
import re

from .retrieval import tokenize
from .schemas import QueryRecord


def query_features(query: QueryRecord) -> dict[str, float]:
    """Inference-time surface features only.

    Gold risk level, gold query type, expected fallback and gold disaster label
    are deliberately excluded to prevent label leakage into the router.
    """

    tokens = tokenize(query.text)
    compact = re.sub(r"\s+", "", query.text.lower())
    urgency_terms = ("立即", "马上", "快", "救命", "昏迷", "呼吸", "着火", "浓烟", "被困")
    context_terms = (
        "家",
        "室内",
        "室外",
        "楼",
        "路",
        "地点",
        "附近",
        "孩子",
        "老人",
        "伤者",
        "患者",
    )
    hazard_terms = (
        "火",
        "烟",
        "洪水",
        "积水",
        "地震",
        "中毒",
        "触电",
        "受伤",
        "雷",
        "暴雨",
        "高温",
        "结冰",
    )
    negations = ("不", "没", "无", "不要", "不能", "禁止", "避免")
    connectors = ("并且", "同时", "还", "另外", "然后", "以及")
    generic = compact in {
        "怎么办",
        "怎么办？",
        "怎么处理",
        "怎么处理？",
        "现在怎么办",
        "现在怎么办？",
        "救命",
    }
    return {
        "token_count": float(len(tokens)),
        "character_count": float(len(compact)),
        "has_question_mark": float("?" in query.text or "？" in query.text),
        "urgency_term_count": float(sum(term in compact for term in urgency_terms)),
        "hazard_term_count": float(sum(term in compact for term in hazard_terms)),
        "context_term_count": float(sum(term in compact for term in context_terms)),
        "negation_count": float(sum(compact.count(term) for term in negations)),
        "multi_intent_connector_count": float(
            sum(compact.count(term) for term in connectors)
        ),
        "has_numeric_detail": float(bool(re.search(r"\d", compact))),
        "surface_insufficient_information": float(
            generic or len(compact) < 6
        ),
    }


def retrieval_features(scores: list[float]) -> dict[str, float]:
    if not scores:
        return {
            "retrieval_top_score": 0.0,
            "retrieval_margin": 0.0,
            "retrieval_entropy": 0.0,
        }
    positive = [max(score, 0.0) for score in scores]
    top = positive[0]
    margin = top - positive[1] if len(positive) > 1 else top
    total = sum(positive)
    entropy = 0.0
    if total > 0:
        probabilities = [value / total for value in positive if value > 0]
        entropy = -sum(value * math.log(value) for value in probabilities)
    return {
        "retrieval_top_score": top,
        "retrieval_margin": margin,
        "retrieval_entropy": entropy,
    }
