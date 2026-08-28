#!/usr/bin/env python3
"""计算输入级协议 Gold 的仲裁前 A/B 一致性。

只接受两份独立原始 CSV。脚本不会读取仲裁结果，也不会修改输入文件。
仅使用 Python 标准库，便于在隔离环境中复算。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


CATEGORICAL_FIELDS = (
    "scope_state",
    "hazard_family_id",
    "risk_state",
    "escalation_required",
    "recommended_response_mode",
)
ORDERED_FIELDS = {"risk_severity": ("S0", "S1", "S2", "S3")}
SET_FIELDS = (
    "query_intent_ids",
    "risk_trigger_ids",
    "evidence_ids",
    "required_action_ids",
    "critical_action_ids",
    "prohibited_action_ids",
    "constraint_ids",
)
PAIR_LOCK_FIELDS = (
    "annotation_phase",
    "blind_batch_id",
    "query_id",
    "source_group_id",
    "query_text",
    "observable_context_json",
    "manual_version",
    "protocol_corpus_version",
    "ontology_version",
)
REQUIRED_COLUMNS = set(
    PAIR_LOCK_FIELDS
    + CATEGORICAL_FIELDS
    + tuple(ORDERED_FIELDS)
    + SET_FIELDS
    + (
        "annotator_id",
        "evidence_gap",
        "evidence_span_refs_json",
        "uncertainty_code",
        "confidence",
        "rationale",
        "completed_at",
    )
)

ENUMS = {
    "annotation_phase": {"TRAINING", "PILOT", "FORMAL"},
    "scope_state": {"IN_SCOPE", "OUT_OF_SCOPE", "UNKNOWN"},
    "risk_state": {"POSITIVE", "NEGATIVE", "UNKNOWN"},
    "risk_severity": {"S0", "S1", "S2", "S3"},
    "escalation_required": {"YES", "NO", "UNKNOWN"},
    "recommended_response_mode": {
        "DIRECT_GUIDANCE",
        "CONDITIONAL_GUIDANCE",
        "SAFE_FALLBACK",
    },
    "uncertainty_code": {
        "NONE",
        "INSUFFICIENT_QUERY",
        "NO_APPLICABLE_PROTOCOL",
        "CONFLICTING_PROTOCOLS",
        "JURISDICTION_MISMATCH",
        "POPULATION_MISMATCH",
        "OUT_OF_SCOPE",
        "ONTOLOGY_GAP",
        "OTHER",
    },
}

DEFAULT_GATES = {
    "minimum_paired_items": 25,
    "scope_state_kappa_min": 0.80,
    "scope_state_raw_agreement_min": 0.92,
    "risk_state_kappa_min": 0.75,
    "risk_state_raw_agreement_min": 0.84,
    "risk_severity_quadratic_kappa_min": 0.75,
    "risk_severity_raw_agreement_min": 0.72,
    "escalation_required_kappa_min": 0.80,
    "escalation_required_raw_agreement_min": 0.88,
    "recommended_response_mode_kappa_min": 0.75,
    "recommended_response_mode_raw_agreement_min": 0.80,
    "risk_trigger_ids_mean_iou_min": 0.67,
    "evidence_ids_mean_iou_min": 0.67,
    "required_action_ids_mean_iou_min": 0.67,
    "critical_action_ids_mean_iou_min": 0.67,
    "prohibited_action_ids_mean_iou_min": 0.67,
    "constraint_ids_mean_iou_min": 0.67,
    "severe_severity_disagreement_max": 0,
    "required_prohibited_conflict_max": 0,
    "critical_not_required_conflict_max": 0,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def parse_set(value: str) -> frozenset[str]:
    if not value.strip():
        return frozenset()
    items = [item.strip() for item in value.split("|") if item.strip()]
    if len(items) != len(set(items)):
        raise ValueError(f"集合字段包含重复 ID: {value}")
    return frozenset(items)


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"布尔字段必须是 true/false，实际为: {value!r}")


def read_csv(path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    rows: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"{path} 缺少字段: {', '.join(missing)}")
        for line_no, raw in enumerate(reader, start=2):
            row = {key: (value or "").strip() for key, value in raw.items()}
            query_id = row["query_id"]
            if not query_id:
                errors.append(f"line {line_no}: query_id 为空")
                continue
            if query_id in rows:
                errors.append(f"line {line_no}: query_id 重复: {query_id}")
                continue
            try:
                for field, allowed in ENUMS.items():
                    if row[field] not in allowed:
                        raise ValueError(f"{field}={row[field]!r} 不在受控值中")
                row["evidence_gap"] = parse_bool(row["evidence_gap"])
                for field in SET_FIELDS:
                    row[field] = parse_set(row[field])
                observable_context = json.loads(row["observable_context_json"])
                if not isinstance(observable_context, dict):
                    raise ValueError("observable_context_json 必须是 JSON object")
                evidence_spans = json.loads(row["evidence_span_refs_json"])
                if not isinstance(evidence_spans, list):
                    raise ValueError("evidence_span_refs_json 必须是 JSON array")
                for span in evidence_spans:
                    if not isinstance(span, dict) or not span.get("evidence_id") or not span.get(
                        "span_ref"
                    ):
                        raise ValueError("每个 evidence span 必须包含 evidence_id 和 span_ref")
                    if span["evidence_id"] not in row["evidence_ids"]:
                        raise ValueError("evidence span 引用了 evidence_ids 之外的 ID")
                row["observable_context"] = observable_context
                row["evidence_span_refs"] = evidence_spans
                confidence = int(row["confidence"])
                if confidence < 1 or confidence > 5:
                    raise ValueError("confidence 必须为 1–5")
                row["confidence"] = confidence
                if not row["annotator_id"]:
                    raise ValueError("annotator_id 为空")
                if not row["source_group_id"]:
                    raise ValueError("source_group_id 为空")
                if not row["query_text"]:
                    raise ValueError("query_text 为空")
                if not row["rationale"]:
                    raise ValueError("rationale 为空")
                if row["risk_state"] == "POSITIVE" and not row["risk_trigger_ids"]:
                    raise ValueError("risk_state=POSITIVE 但 risk_trigger_ids 为空")
                if not row["evidence_gap"] and not row["evidence_ids"]:
                    raise ValueError("evidence_gap=false 但 evidence_ids 为空")
                if (row["risk_state"] == "UNKNOWN" or row["evidence_gap"]) and row[
                    "uncertainty_code"
                ] == "NONE":
                    raise ValueError("Unknown/evidence gap 必须填写 uncertainty_code")
                if not row["critical_action_ids"].issubset(row["required_action_ids"]):
                    raise ValueError("critical_action_ids 不是 required_action_ids 子集")
                if row["required_action_ids"] & row["prohibited_action_ids"]:
                    raise ValueError("required_action_ids 与 prohibited_action_ids 有交集")
                if row["annotation_phase"] == "FORMAL":
                    review_ids = set().union(*(row[field] for field in SET_FIELDS))
                    if any(item.endswith("_OTHER_REVIEW") for item in review_ids):
                        raise ValueError("正式记录仍包含 REVIEW 占位 ID")
                    if row["evidence_ids"] and not row["evidence_span_refs"]:
                        raise ValueError("正式记录有 evidence_ids 但缺少 evidence_span_refs")
                completed_at = datetime.fromisoformat(row["completed_at"].replace("Z", "+00:00"))
                if completed_at.tzinfo is None:
                    raise ValueError("completed_at 必须包含时区")
            except (ValueError, TypeError) as exc:
                errors.append(f"line {line_no} query_id={query_id}: {exc}")
                continue
            rows[query_id] = row
    return rows, errors


def exact_agreement(values_a: Iterable[Any], values_b: Iterable[Any]) -> float | None:
    pairs = list(zip(values_a, values_b))
    if not pairs:
        return None
    return sum(a == b for a, b in pairs) / len(pairs)


def cohen_kappa(values_a: Iterable[str], values_b: Iterable[str]) -> float | None:
    pairs = list(zip(values_a, values_b))
    if not pairs:
        return None
    n = len(pairs)
    counts_a = Counter(a for a, _ in pairs)
    counts_b = Counter(b for _, b in pairs)
    observed = sum(a == b for a, b in pairs) / n
    categories = set(counts_a) | set(counts_b)
    expected = sum((counts_a[c] / n) * (counts_b[c] / n) for c in categories)
    if math.isclose(1.0 - expected, 0.0):
        return 1.0 if math.isclose(observed, 1.0) else None
    return (observed - expected) / (1.0 - expected)


def quadratic_weighted_kappa(
    values_a: Iterable[str], values_b: Iterable[str], order: tuple[str, ...]
) -> float | None:
    pairs = list(zip(values_a, values_b))
    if not pairs:
        return None
    index = {value: idx for idx, value in enumerate(order)}
    k = len(order)
    n = len(pairs)
    observed = [[0 for _ in range(k)] for _ in range(k)]
    rows = Counter()
    cols = Counter()
    for a, b in pairs:
        i, j = index[a], index[b]
        observed[i][j] += 1
        rows[i] += 1
        cols[j] += 1
    denominator = float((k - 1) ** 2)
    observed_weighted = 0.0
    expected_weighted = 0.0
    for i in range(k):
        for j in range(k):
            weight = ((i - j) ** 2) / denominator
            observed_weighted += weight * observed[i][j] / n
            expected_weighted += weight * (rows[i] * cols[j]) / (n * n)
    if math.isclose(expected_weighted, 0.0):
        return 1.0 if math.isclose(observed_weighted, 0.0) else None
    return 1.0 - observed_weighted / expected_weighted


def confusion(values_a: Iterable[str], values_b: Iterable[str]) -> dict[str, dict[str, int]]:
    pairs = list(zip(values_a, values_b))
    categories = sorted(set(a for a, _ in pairs) | set(b for _, b in pairs))
    matrix = {a: {b: 0 for b in categories} for a in categories}
    for a, b in pairs:
        matrix[a][b] += 1
    return matrix


def positive_agreement(values_a: Iterable[str], values_b: Iterable[str], positive: str) -> float | None:
    pairs = list(zip(values_a, values_b))
    positives_a = sum(a == positive for a, _ in pairs)
    positives_b = sum(b == positive for _, b in pairs)
    both = sum(a == positive and b == positive for a, b in pairs)
    denominator = positives_a + positives_b
    return (2 * both / denominator) if denominator else None


def set_pair_metrics(a: frozenset[str], b: frozenset[str]) -> tuple[float, float, float]:
    if not a and not b:
        return 1.0, 1.0, 1.0
    intersection = len(a & b)
    union = len(a | b)
    iou = intersection / union if union else 1.0
    dice = 2 * intersection / (len(a) + len(b)) if (a or b) else 1.0
    exact = 1.0 if a == b else 0.0
    return exact, iou, dice


def percentile(values: list[float], q: float) -> float | None:
    clean = sorted(v for v in values if v is not None and math.isfinite(v))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean[lower]
    weight = position - lower
    return clean[lower] * (1 - weight) + clean[upper] * weight


def ci(values: list[float]) -> list[float | None]:
    return [percentile(values, 0.025), percentile(values, 0.975)]


def categorical_metric(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    a = [row["a"][field] for row in rows]
    b = [row["b"][field] for row in rows]
    result: dict[str, Any] = {
        "n": len(rows),
        "raw_agreement": exact_agreement(a, b),
        "cohen_kappa": cohen_kappa(a, b),
        "confusion_a_rows_b_columns": confusion(a, b),
        "distribution_a": dict(sorted(Counter(a).items())),
        "distribution_b": dict(sorted(Counter(b).items())),
    }
    if field == "escalation_required":
        result["positive_agreement_yes"] = positive_agreement(a, b, "YES")
    return result


def ordered_metric(rows: list[dict[str, Any]], field: str, order: tuple[str, ...]) -> dict[str, Any]:
    a = [row["a"][field] for row in rows]
    b = [row["b"][field] for row in rows]
    return {
        "n": len(rows),
        "raw_agreement": exact_agreement(a, b),
        "quadratic_weighted_kappa": quadratic_weighted_kappa(a, b, order),
        "confusion_a_rows_b_columns": confusion(a, b),
        "distribution_a": dict(sorted(Counter(a).items())),
        "distribution_b": dict(sorted(Counter(b).items())),
    }


def set_metric(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [set_pair_metrics(row["a"][field], row["b"][field]) for row in rows]
    exacts = [value[0] for value in values]
    ious = [value[1] for value in values]
    dices = [value[2] for value in values]
    both_empty = sum(not row["a"][field] and not row["b"][field] for row in rows)
    one_empty = sum(bool(row["a"][field]) != bool(row["b"][field]) for row in rows)
    return {
        "n": len(rows),
        "exact_match_rate": statistics.fmean(exacts) if exacts else None,
        "mean_iou": statistics.fmean(ious) if ious else None,
        "median_iou": statistics.median(ious) if ious else None,
        "mean_dice": statistics.fmean(dices) if dices else None,
        "median_dice": statistics.median(dices) if dices else None,
        "both_empty_count": both_empty,
        "one_empty_count": one_empty,
        "both_nonempty_count": len(rows) - both_empty - one_empty,
    }


def bootstrap_intervals(
    rows: list[dict[str, Any]], iterations: int, seed: int
) -> dict[str, dict[str, list[float | None]]]:
    if iterations <= 0:
        return {}
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[row["a"]["source_group_id"]].append(row)
    cluster_ids = sorted(clusters)
    rng = random.Random(seed)
    samples: dict[str, dict[str, list[float]]] = {
        "categorical": defaultdict(list),
        "ordered": defaultdict(list),
        "sets_iou": defaultdict(list),
        "sets_dice": defaultdict(list),
        "sets_exact": defaultdict(list),
    }
    for _ in range(iterations):
        selected: list[dict[str, Any]] = []
        for cluster_id in rng.choices(cluster_ids, k=len(cluster_ids)):
            selected.extend(clusters[cluster_id])
        for field in CATEGORICAL_FIELDS:
            value = cohen_kappa(
                (row["a"][field] for row in selected),
                (row["b"][field] for row in selected),
            )
            if value is not None:
                samples["categorical"][field].append(value)
        for field, order in ORDERED_FIELDS.items():
            value = quadratic_weighted_kappa(
                (row["a"][field] for row in selected),
                (row["b"][field] for row in selected),
                order,
            )
            if value is not None:
                samples["ordered"][field].append(value)
        for field in SET_FIELDS:
            metrics = [set_pair_metrics(row["a"][field], row["b"][field]) for row in selected]
            if metrics:
                samples["sets_exact"][field].append(statistics.fmean(v[0] for v in metrics))
                samples["sets_iou"][field].append(statistics.fmean(v[1] for v in metrics))
                samples["sets_dice"][field].append(statistics.fmean(v[2] for v in metrics))
    return {
        section: {field: ci(values) for field, values in fields.items()}
        for section, fields in samples.items()
    }


def load_gates(path: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    if path is None:
        return DEFAULT_GATES.copy(), {"status": "built_in_provisional", "approval": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    thresholds = DEFAULT_GATES.copy()
    thresholds.update(payload.get("thresholds", {}))
    metadata = {
        "path": str(path),
        "sha256": sha256_file(path),
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status", "unknown"),
        "approval": payload.get("approval", {}),
    }
    return thresholds, metadata


def is_gate_approved(metadata: dict[str, Any]) -> bool:
    if metadata.get("status") != "approved":
        return False
    approval = metadata.get("approval", {})
    return all(
        approval.get(key)
        for key in (
            "domain_reviewer_id",
            "research_supervisor_id",
            "statistics_reviewer_id",
            "approved_at",
        )
    )


def validate_pair(
    rows_a: dict[str, dict[str, Any]], rows_b: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    ids_a, ids_b = set(rows_a), set(rows_b)
    if ids_a != ids_b:
        missing_a = sorted(ids_b - ids_a)
        missing_b = sorted(ids_a - ids_b)
        errors.append(f"A 缺少 query_id: {missing_a}")
        errors.append(f"B 缺少 query_id: {missing_b}")
    paired: list[dict[str, Any]] = []
    for query_id in sorted(ids_a & ids_b):
        a, b = rows_a[query_id], rows_b[query_id]
        for field in PAIR_LOCK_FIELDS:
            if a[field] != b[field]:
                errors.append(f"{query_id}: 配对锁定字段不一致 {field}")
        if a["annotator_id"] == b["annotator_id"]:
            errors.append(f"{query_id}: A/B annotator_id 相同")
        paired.append({"query_id": query_id, "a": a, "b": b})
    return paired, errors


def disagreement_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    disagreements: list[dict[str, Any]] = []
    severe: list[str] = []
    s3_no_escalation: list[dict[str, str]] = []
    for row in rows:
        fields: list[str] = []
        for field in CATEGORICAL_FIELDS + tuple(ORDERED_FIELDS) + SET_FIELDS:
            if row["a"][field] != row["b"][field]:
                fields.append(field)
        if row["a"]["evidence_gap"] != row["b"]["evidence_gap"]:
            fields.append("evidence_gap")
        if row["a"]["uncertainty_code"] != row["b"]["uncertainty_code"]:
            fields.append("uncertainty_code")
        if fields:
            disagreements.append({"query_id": row["query_id"], "fields": fields})
        levels = {row["a"]["risk_severity"], row["b"]["risk_severity"]}
        if "S3" in levels and ("S0" in levels or "S1" in levels):
            severe.append(row["query_id"])
        for reviewer in ("a", "b"):
            if (
                row[reviewer]["risk_severity"] == "S3"
                and row[reviewer]["escalation_required"] == "NO"
            ):
                s3_no_escalation.append(
                    {"query_id": row["query_id"], "reviewer": reviewer.upper()}
                )
    return {
        "disagreement_query_count": len(disagreements),
        "disagreements": disagreements,
        "severe_severity_disagreement_count": len(severe),
        "severe_severity_disagreement_query_ids": severe,
        "s3_with_escalation_no": s3_no_escalation,
    }


def structural_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    required_prohibited: list[dict[str, Any]] = []
    critical_not_required: list[dict[str, Any]] = []
    for row in rows:
        for reviewer in ("a", "b"):
            record = row[reviewer]
            overlap = sorted(record["required_action_ids"] & record["prohibited_action_ids"])
            if overlap:
                required_prohibited.append(
                    {"query_id": row["query_id"], "reviewer": reviewer.upper(), "ids": overlap}
                )
            invalid_critical = sorted(record["critical_action_ids"] - record["required_action_ids"])
            if invalid_critical:
                critical_not_required.append(
                    {
                        "query_id": row["query_id"],
                        "reviewer": reviewer.upper(),
                        "ids": invalid_critical,
                    }
                )
    return {
        "required_prohibited_conflict_count": len(required_prohibited),
        "required_prohibited_conflicts": required_prohibited,
        "critical_not_required_conflict_count": len(critical_not_required),
        "critical_not_required_conflicts": critical_not_required,
    }


def gate_evaluation(
    metrics: dict[str, Any], audits: dict[str, Any], thresholds: dict[str, Any]
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, value: float | int | None, operator: str, threshold: float | int) -> None:
        passed = False
        if value is not None:
            passed = value >= threshold if operator == ">=" else value <= threshold
        checks.append(
            {
                "name": name,
                "value": value,
                "operator": operator,
                "threshold": threshold,
                "passed": passed,
            }
        )

    add(
        "paired_item_count",
        metrics["categorical"]["risk_state"]["n"],
        ">=",
        thresholds["minimum_paired_items"],
    )
    add(
        "scope_state_kappa",
        metrics["categorical"]["scope_state"]["cohen_kappa"],
        ">=",
        thresholds["scope_state_kappa_min"],
    )
    add(
        "scope_state_raw_agreement",
        metrics["categorical"]["scope_state"]["raw_agreement"],
        ">=",
        thresholds["scope_state_raw_agreement_min"],
    )
    add(
        "risk_state_kappa",
        metrics["categorical"]["risk_state"]["cohen_kappa"],
        ">=",
        thresholds["risk_state_kappa_min"],
    )
    add(
        "risk_state_raw_agreement",
        metrics["categorical"]["risk_state"]["raw_agreement"],
        ">=",
        thresholds["risk_state_raw_agreement_min"],
    )
    add(
        "risk_severity_quadratic_kappa",
        metrics["ordered"]["risk_severity"]["quadratic_weighted_kappa"],
        ">=",
        thresholds["risk_severity_quadratic_kappa_min"],
    )
    add(
        "risk_severity_raw_agreement",
        metrics["ordered"]["risk_severity"]["raw_agreement"],
        ">=",
        thresholds["risk_severity_raw_agreement_min"],
    )
    add(
        "escalation_required_kappa",
        metrics["categorical"]["escalation_required"]["cohen_kappa"],
        ">=",
        thresholds["escalation_required_kappa_min"],
    )
    add(
        "escalation_required_raw_agreement",
        metrics["categorical"]["escalation_required"]["raw_agreement"],
        ">=",
        thresholds["escalation_required_raw_agreement_min"],
    )
    add(
        "recommended_response_mode_kappa",
        metrics["categorical"]["recommended_response_mode"]["cohen_kappa"],
        ">=",
        thresholds["recommended_response_mode_kappa_min"],
    )
    add(
        "recommended_response_mode_raw_agreement",
        metrics["categorical"]["recommended_response_mode"]["raw_agreement"],
        ">=",
        thresholds["recommended_response_mode_raw_agreement_min"],
    )
    for field in (
        "risk_trigger_ids",
        "evidence_ids",
        "required_action_ids",
        "critical_action_ids",
        "prohibited_action_ids",
        "constraint_ids",
    ):
        add(
            f"{field}_mean_iou",
            metrics["sets"][field]["mean_iou"],
            ">=",
            thresholds[f"{field}_mean_iou_min"],
        )
    add(
        "severe_severity_disagreement_count",
        audits["disagreement"]["severe_severity_disagreement_count"],
        "<=",
        thresholds["severe_severity_disagreement_max"],
    )
    add(
        "required_prohibited_conflict_count",
        audits["structural"]["required_prohibited_conflict_count"],
        "<=",
        thresholds["required_prohibited_conflict_max"],
    )
    add(
        "critical_not_required_conflict_count",
        audits["structural"]["critical_not_required_conflict_count"],
        "<=",
        thresholds["critical_not_required_conflict_max"],
    )
    failures = [check for check in checks if not check["passed"]]
    blocking_names = {
        "paired_item_count",
        "severe_severity_disagreement_count",
        "required_prohibited_conflict_count",
        "critical_not_required_conflict_count",
    }
    if any(check["name"] in blocking_names for check in failures):
        metric_decision = "BLOCKED"
    elif failures:
        metric_decision = "REVIEW_REQUIRED"
    else:
        metric_decision = "PASS_FOR_ADJUDICATION"
    return {"metric_decision": metric_decision, "checks": checks}


def format_number(value: Any) -> str:
    if value is None:
        return "NA"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# 输入级 Gold 仲裁前一致性报告",
        "",
        f"生成时间：{report['generated_at']}",
        f"配对记录：{report['n_paired']}",
        f"指标门禁：`{report['gate_evaluation']['metric_decision']}`",
        f"正式门禁：`{report['gate_evaluation']['formal_decision']}`",
        "",
        "## 输入文件",
        "",
        f"- Reviewer A：`{report['inputs']['reviewer_a']['path']}`",
        f"  - SHA-256：`{report['inputs']['reviewer_a']['sha256']}`",
        f"- Reviewer B：`{report['inputs']['reviewer_b']['path']}`",
        f"  - SHA-256：`{report['inputs']['reviewer_b']['sha256']}`",
        "",
        "## 分类与有序字段",
        "",
        "| 字段 | n | 原始一致率 | Kappa | 95% CI |",
        "|---|---:|---:|---:|---:|",
    ]
    bootstrap = report.get("bootstrap_95ci", {})
    for field, metric in report["metrics"]["categorical"].items():
        interval = bootstrap.get("categorical", {}).get(field, [None, None])
        lines.append(
            f"| {field} | {metric['n']} | {format_number(metric['raw_agreement'])} | "
            f"{format_number(metric['cohen_kappa'])} | "
            f"[{format_number(interval[0])}, {format_number(interval[1])}] |"
        )
    for field, metric in report["metrics"]["ordered"].items():
        interval = bootstrap.get("ordered", {}).get(field, [None, None])
        lines.append(
            f"| {field} | {metric['n']} | {format_number(metric['raw_agreement'])} | "
            f"{format_number(metric['quadratic_weighted_kappa'])} | "
            f"[{format_number(interval[0])}, {format_number(interval[1])}] |"
        )
    lines.extend(
        [
            "",
            "## 集合字段",
            "",
            "| 字段 | Exact | Mean IoU | IoU 95% CI | Mean Dice | 双方空/单边空/双方非空 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for field, metric in report["metrics"]["sets"].items():
        interval = bootstrap.get("sets_iou", {}).get(field, [None, None])
        lines.append(
            f"| {field} | {format_number(metric['exact_match_rate'])} | "
            f"{format_number(metric['mean_iou'])} | "
            f"[{format_number(interval[0])}, {format_number(interval[1])}] | "
            f"{format_number(metric['mean_dice'])} | "
            f"{metric['both_empty_count']}/{metric['one_empty_count']}/{metric['both_nonempty_count']} |"
        )
    lines.extend(
        [
            "",
            "## 质量门禁",
            "",
            "| 检查 | 实际值 | 条件 | 门槛 | 通过 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for check in report["gate_evaluation"]["checks"]:
        lines.append(
            f"| {check['name']} | {format_number(check['value'])} | {check['operator']} | "
            f"{format_number(check['threshold'])} | {'是' if check['passed'] else '否'} |"
        )
    disagreement = report["audits"]["disagreement"]
    structural = report["audits"]["structural"]
    lines.extend(
        [
            "",
            "## 分歧与阻断项",
            "",
            f"- 存在任意内容分歧的查询：{disagreement['disagreement_query_count']}",
            f"- S3 对 S0/S1 严重分歧：{disagreement['severe_severity_disagreement_count']}",
            f"- required/prohibited 冲突：{structural['required_prohibited_conflict_count']}",
            f"- critical 非 required 冲突：{structural['critical_not_required_conflict_count']}",
            "",
            "### 待仲裁查询",
            "",
        ]
    )
    if disagreement["disagreements"]:
        for item in disagreement["disagreements"]:
            lines.append(f"- `{item['query_id']}`：{', '.join(item['fields'])}")
    else:
        lines.append("- 无内容分歧。仍须按协议完成高风险复核和低风险抽检。")
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "本报告使用仲裁前 A/B 原始标签，只衡量标注一致性。它不证明标签无偏、医学正确、",
            "临床有效或系统在真实灾害中安全。门禁通过仅表示该批次可以进入领域仲裁。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="计算输入级协议 Gold 的仲裁前 A/B 一致性")
    parser.add_argument("--reviewer-a", required=True, type=Path)
    parser.add_argument("--reviewer-b", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-md", required=True, type=Path)
    parser.add_argument("--gates", type=Path)
    parser.add_argument("--bootstrap", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260821)
    args = parser.parse_args()

    rows_a, errors_a = read_csv(args.reviewer_a)
    rows_b, errors_b = read_csv(args.reviewer_b)
    paired, pair_errors = validate_pair(rows_a, rows_b)
    input_errors = errors_a + errors_b + pair_errors
    if input_errors:
        for error in input_errors:
            print(f"ERROR: {error}")
        return 2
    if not paired:
        print("ERROR: 没有可配对记录")
        return 2

    metrics = {
        "categorical": {field: categorical_metric(paired, field) for field in CATEGORICAL_FIELDS},
        "ordered": {
            field: ordered_metric(paired, field, order) for field, order in ORDERED_FIELDS.items()
        },
        "sets": {field: set_metric(paired, field) for field in SET_FIELDS},
    }
    audits = {
        "disagreement": disagreement_audit(paired),
        "structural": structural_audit(paired),
    }
    thresholds, gate_metadata = load_gates(args.gates)
    evaluation = gate_evaluation(metrics, audits, thresholds)
    gate_approved = is_gate_approved(gate_metadata)
    evaluation["gate_profile_approved"] = gate_approved
    evaluation["formal_decision"] = (
        evaluation["metric_decision"]
        if gate_approved
        else "REVIEW_REQUIRED_UNTIL_GATE_PROFILE_APPROVED"
    )

    report = {
        "schema_version": "input-gold-agreement-report-v1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_paired": len(paired),
        "source_group_count": len({row["a"]["source_group_id"] for row in paired}),
        "inputs": {
            "reviewer_a": {
                "path": str(args.reviewer_a),
                "sha256": sha256_file(args.reviewer_a),
                "rows": len(rows_a),
                "annotator_ids": sorted({row["annotator_id"] for row in rows_a.values()}),
            },
            "reviewer_b": {
                "path": str(args.reviewer_b),
                "sha256": sha256_file(args.reviewer_b),
                "rows": len(rows_b),
                "annotator_ids": sorted({row["annotator_id"] for row in rows_b.values()}),
            },
        },
        "bootstrap": {
            "unit": "source_group_id",
            "iterations": args.bootstrap,
            "seed": args.seed,
        },
        "metrics": metrics,
        "bootstrap_95ci": bootstrap_intervals(paired, args.bootstrap, args.seed),
        "audits": audits,
        "gate_profile": gate_metadata,
        "gate_thresholds": thresholds,
        "gate_evaluation": evaluation,
        "interpretation_boundary": (
            "Agreement is computed from locked pre-adjudication labels. It does not establish "
            "unbiased labels, clinical correctness, or real-world safety."
        ),
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output_md.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "n_paired": len(paired),
                "metric_decision": evaluation["metric_decision"],
                "formal_decision": evaluation["formal_decision"],
                "output_json": str(args.output_json),
                "output_md": str(args.output_md),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
