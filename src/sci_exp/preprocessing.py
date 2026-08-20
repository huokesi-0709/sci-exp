from __future__ import annotations

import hashlib
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from .schemas import QueryRecord
from .splitting import group_split
from .validation import dataset_summary


PREPROCESSING_VERSION = "1.1"

_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
_HORIZONTAL_SPACE = re.compile(r"[^\S\r\n]+")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_REPEATED_CHARACTER = re.compile(r"(.)\1{49,}")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_CN_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
_CN_ID = re.compile(r"(?<!\d)\d{17}[\dXx](?![\dXx])")
_COORDINATE = re.compile(
    r"(?i)(?:lat(?:itude)?|lon(?:gitude)?|纬度|经度)"
    r"\s*[:：=]?\s*[-+]?\d{1,3}(?:\.\d+)?"
)
_SHORT_EMERGENCY_CUES = frozenset(
    "水血喘呼吸火烟困冷热痛伤震洪电网救命求救昏晕出血被困胸"
)

_REQUIRED_QUERY_FIELDS = (
    "query_id",
    "text",
    "disaster_type",
    "query_type",
    "risk_level",
    "language",
    "should_fallback",
    "source_group_id",
)
_OPTIONAL_LIST_FIELDS = (
    "gold_evidence_ids",
    "required_actions",
    "prohibited_actions",
)


@dataclass(frozen=True)
class PreprocessResult:
    records: list[dict[str, Any]]
    quarantine: list[dict[str, Any]]
    events: list[dict[str, Any]]
    report: dict[str, Any]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _ZERO_WIDTH.sub("", text)
    text = _HORIZONTAL_SPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _EXCESS_BLANK_LINES.sub("\n\n", text).strip()


def redact_sensitive_text(value: str) -> tuple[str, list[str]]:
    redacted = value
    detected: list[str] = []
    patterns = (
        ("email", _EMAIL, "[已遮盖邮箱]"),
        ("phone", _CN_PHONE, "[已遮盖手机号]"),
        ("national_id", _CN_ID, "[已遮盖证件号]"),
        ("precise_coordinate", _COORDINATE, "[已遮盖精确坐标]"),
    )
    for name, pattern, replacement in patterns:
        if pattern.search(redacted):
            detected.append(name)
            redacted = pattern.sub(replacement, redacted)
    return redacted, detected


def preprocess_query_rows(
    rows: Iterable[dict[str, Any]],
    *,
    seed: int = 42,
    min_characters: int = 4,
    max_characters: int = 1000,
    augment_train_copies: int = 0,
    preserve_existing_splits: bool = False,
) -> PreprocessResult:
    if min_characters < 1:
        raise ValueError("min_characters must be positive")
    if max_characters < min_characters:
        raise ValueError("max_characters must be >= min_characters")
    if augment_train_copies < 0 or augment_train_copies > 2:
        raise ValueError("augment_train_copies must be in 0..2")

    input_rows = list(rows)
    candidates: list[tuple[int, dict[str, Any]]] = []
    quarantine: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for row_number, raw in enumerate(input_rows, start=1):
        normalized, reasons, warnings = _normalize_query_row(
            raw,
            row_number=row_number,
            min_characters=min_characters,
            max_characters=max_characters,
        )
        for warning in warnings:
            events.append(
                {
                    "row_number": row_number,
                    "query_id": str(raw.get("query_id", "")),
                    "level": "warning",
                    "code": warning,
                }
            )
        if reasons:
            source = normalized if normalized is not None else raw
            quarantine.append(_quarantine_query(source, row_number, reasons))
            for reason in reasons:
                events.append(
                    {
                        "row_number": row_number,
                        "query_id": str(raw.get("query_id", "")),
                        "level": "error",
                        "code": reason,
                    }
                )
            continue
        assert normalized is not None
        candidates.append((row_number, normalized))

    candidates, duplicate_quarantine, duplicate_events = (
        _resolve_query_duplicates(candidates)
    )
    quarantine.extend(duplicate_quarantine)
    events.extend(duplicate_events)

    query_objects = [QueryRecord.from_dict(row) for _, row in candidates]
    if preserve_existing_splits:
        allowed_splits = {
            "train",
            "valid",
            "cal_op",
            "cal_ch",
            "test_op",
            "test_ch",
        }
        invalid = [
            query.query_id
            for query in query_objects
            if query.split not in allowed_splits
        ]
        if invalid:
            raise ValueError(
                "preserve_existing_splits requires one of the six frozen "
                f"splits; invalid query_ids={invalid[:10]}"
            )
        group_splits: dict[str, set[str]] = defaultdict(set)
        for query in query_objects:
            group_splits[query.source_group_id].add(query.split)
        leaking = {
            group: sorted(splits)
            for group, splits in group_splits.items()
            if len(splits) > 1
        }
        if leaking:
            raise ValueError(
                "frozen source groups leak across splits: "
                f"{dict(list(leaking.items())[:10])}"
            )
        split_objects = query_objects
    else:
        split_objects = group_split(query_objects, seed=seed)
    base_records = [query.to_dict() for query in split_objects]
    augmented = _augment_training_queries(
        split_objects,
        copies=augment_train_copies,
    )
    records = base_records + [query.to_dict() for query in augmented]
    records.sort(key=lambda row: (str(row["split"]), str(row["query_id"])))

    summary = dataset_summary(QueryRecord.from_dict(row) for row in records)
    report = {
        "schema_version": "1.0",
        "preprocessing_version": PREPROCESSING_VERSION,
        "seed": seed,
        "parameters": {
            "min_characters": min_characters,
            "max_characters": max_characters,
            "augment_train_copies": augment_train_copies,
            "preserve_existing_splits": preserve_existing_splits,
        },
        "counts": {
            "input_rows": len(input_rows),
            "accepted_base_rows": len(base_records),
            "augmented_rows": len(augmented),
            "output_rows": len(records),
            "quarantined_rows": len(quarantine),
            "warning_events": sum(
                event["level"] == "warning" for event in events
            ),
            "error_events": sum(event["level"] == "error" for event in events),
        },
        "quarantine_reasons": dict(
            sorted(
                Counter(
                    reason
                    for item in quarantine
                    for reason in item.get("reasons", [])
                ).items()
            )
        ),
        "summary": summary,
        "quality_gates": {
            "no_detected_sensitive_text_in_output": True,
            "group_split_before_augmentation": True,
            "frozen_splits_preserved": preserve_existing_splits,
            "labels_not_imputed": True,
        },
    }
    return PreprocessResult(records, quarantine, events, report)


def _normalize_query_row(
    raw: dict[str, Any],
    *,
    row_number: int,
    min_characters: int,
    max_characters: int,
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    reasons: list[str] = []
    warnings: list[str] = []
    for field in _REQUIRED_QUERY_FIELDS:
        value = raw.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            reasons.append(f"missing_required:{field}")
    if reasons:
        return None, reasons, warnings

    if isinstance(raw["risk_level"], bool) or not isinstance(raw["risk_level"], int):
        reasons.append("invalid_type:risk_level")
    elif raw["risk_level"] not in {0, 1, 2, 3}:
        reasons.append("out_of_range:risk_level")
    if not isinstance(raw["should_fallback"], bool):
        reasons.append("invalid_type:should_fallback")
    for field in _OPTIONAL_LIST_FIELDS:
        value = raw.get(field)
        if value is None:
            warnings.append(f"missing_optional_default_empty:{field}")
        elif not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            reasons.append(f"invalid_type:{field}")
    if reasons:
        return None, reasons, warnings

    text = normalize_text(str(raw["text"]))
    redacted, sensitive_types = redact_sensitive_text(text)
    if sensitive_types:
        reasons.extend(f"sensitive_text:{item}" for item in sensitive_types)
    short_query_challenge = False
    if len(text) < min_characters:
        if _is_meaningful_short_query(
            text,
            risk_level=raw["risk_level"],
            should_fallback=raw["should_fallback"],
        ):
            short_query_challenge = True
            warnings.append("short_query_challenge")
        else:
            reasons.append("text_too_short")
    if len(text) > max_characters:
        reasons.append("text_too_long")
    if _REPEATED_CHARACTER.search(text):
        reasons.append("repeated_character_anomaly")
    if reasons:
        value = dict(raw)
        value["text"] = redacted
        return value, reasons, warnings

    known_fields = {
        *_REQUIRED_QUERY_FIELDS,
        *_OPTIONAL_LIST_FIELDS,
        "split",
    }
    normalized: dict[str, Any] = {
        "query_id": normalize_text(str(raw["query_id"])),
        "text": text,
        "disaster_type": normalize_text(str(raw["disaster_type"])).lower(),
        "query_type": normalize_text(str(raw["query_type"])).lower(),
        "risk_level": int(raw["risk_level"]),
        "language": normalize_text(str(raw["language"])).lower(),
        "should_fallback": raw["should_fallback"],
        "gold_evidence_ids": _normalize_string_list(
            raw.get("gold_evidence_ids") or []
        ),
        "required_actions": _normalize_string_list(
            raw.get("required_actions") or []
        ),
        "prohibited_actions": _normalize_string_list(
            raw.get("prohibited_actions") or []
        ),
        "source_group_id": normalize_text(str(raw["source_group_id"])),
        "split": normalize_text(str(raw.get("split", ""))),
    }
    for key, value in raw.items():
        if key not in known_fields:
            normalized[key] = value
    normalized["preprocessing"] = {
        "version": PREPROCESSING_VERSION,
        "source_row_number": row_number,
        "normalized": True,
        "short_query_challenge": short_query_challenge,
        "query_length_characters": len(text),
    }
    return normalized, [], warnings


def _is_meaningful_short_query(
    text: str,
    *,
    risk_level: int,
    should_fallback: bool,
) -> bool:
    """保留带有明确应急线索的短输入，并标记为挑战样本。"""
    if len(text) < 2 or (risk_level < 1 and not should_fallback):
        return False
    return any(character in _SHORT_EMERGENCY_CUES for character in text)


def _normalize_string_list(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_text(value)
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _resolve_query_duplicates(
    candidates: list[tuple[int, dict[str, Any]]],
) -> tuple[
    list[tuple[int, dict[str, Any]]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    quarantine: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    rejected_rows: set[int] = set()

    by_id: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for item in candidates:
        by_id[str(item[1]["query_id"])].append(item)
    for query_id, items in by_id.items():
        if len(items) <= 1:
            continue
        fingerprints = {_query_fingerprint(row) for _, row in items}
        if len(fingerprints) == 1:
            targets = items[1:]
            reason = "duplicate_exact_query_id"
        else:
            targets = items
            reason = "duplicate_conflicting_query_id"
        for row_number, row in targets:
            rejected_rows.add(row_number)
            quarantine.append(_quarantine_query(row, row_number, [reason]))
            events.append(
                {
                    "row_number": row_number,
                    "query_id": query_id,
                    "level": "error",
                    "code": reason,
                }
            )

    remaining = [item for item in candidates if item[0] not in rejected_rows]
    by_text: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for item in remaining:
        by_text[str(item[1]["text"])].append(item)
    for items in by_text.values():
        groups = {str(row["source_group_id"]) for _, row in items}
        if len(groups) <= 1:
            continue
        for row_number, row in items:
            rejected_rows.add(row_number)
            reason = "normalized_text_cross_group_leakage"
            quarantine.append(_quarantine_query(row, row_number, [reason]))
            events.append(
                {
                    "row_number": row_number,
                    "query_id": str(row["query_id"]),
                    "level": "error",
                    "code": reason,
                }
            )
    accepted = [item for item in candidates if item[0] not in rejected_rows]
    return accepted, quarantine, events


def _query_fingerprint(row: dict[str, Any]) -> str:
    keys = (
        "text",
        "disaster_type",
        "query_type",
        "risk_level",
        "language",
        "should_fallback",
        "gold_evidence_ids",
        "required_actions",
        "prohibited_actions",
        "source_group_id",
    )
    payload = repr(tuple((key, row.get(key)) for key in keys)).encode("utf-8")
    return sha256_bytes(payload)


def _quarantine_query(
    raw: dict[str, Any],
    row_number: int,
    reasons: list[str],
) -> dict[str, Any]:
    value = dict(raw)
    if "text" in value:
        value["text"] = redact_sensitive_text(normalize_text(str(value["text"])))[0]
    return {
        "source_row_number": row_number,
        "query_id": str(value.get("query_id", "")),
        "reasons": sorted(set(reasons)),
        "record": value,
    }


def _augment_training_queries(
    queries: Iterable[QueryRecord],
    *,
    copies: int,
) -> list[QueryRecord]:
    augmented: list[QueryRecord] = []
    for query in queries:
        if query.split != "train":
            continue
        for copy_index in range(1, copies + 1):
            text, augmentation_type = _safe_text_variant(query.text, copy_index)
            if text == query.text:
                continue
            value = query.to_dict()
            value.update(
                {
                    "query_id": f"{query.query_id}__aug{copy_index:02d}",
                    "text": text,
                    "source_group_id": query.source_group_id,
                    "split": "train",
                    "augmentation_parent_id": query.query_id,
                    "augmentation_type": augmentation_type,
                }
            )
            augmented.append(QueryRecord.from_dict(value))
    return augmented


def _safe_text_variant(text: str, copy_index: int) -> tuple[str, str]:
    if copy_index == 1:
        translated = text.translate(
            str.maketrans({"?": "？", ",": "，", ";": "；", ":": "："})
        )
        if translated == text:
            if text.endswith("。"):
                translated = text[:-1]
            elif not text.endswith(("？", "！", "。")):
                translated = f"{text}？"
        return translated, "punctuation_style"
    translated = text.translate(
        str.maketrans({"？": "?", "，": ",", "；": ";", "：": ":"})
    )
    return translated, "ascii_punctuation_style"


def preprocess_resource_rows(
    rows: Iterable[dict[str, Any]],
    *,
    require_energy: bool = True,
    robust_z_threshold: float = 3.5,
) -> PreprocessResult:
    if robust_z_threshold <= 0:
        raise ValueError("robust_z_threshold must be positive")
    input_rows = list(rows)
    accepted: list[dict[str, Any]] = []
    quarantine: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for row_number, raw in enumerate(input_rows, start=1):
        reasons: list[str] = []
        for field in ("status", "query_id", "configuration", "repetition"):
            if field not in raw or raw[field] in (None, ""):
                reasons.append(f"missing_required:{field}")
        if raw.get("status") == "ok":
            if _finite_positive(raw.get("latency_ms")) is None:
                reasons.append("invalid_or_missing:latency_ms")
            telemetry = raw.get("telemetry")
            if not isinstance(telemetry, dict):
                reasons.append("invalid_or_missing:telemetry")
            elif (
                require_energy
                and _finite_nonnegative(telemetry.get("energy_j")) is None
            ):
                reasons.append("invalid_or_missing:energy_j")
        if reasons:
            quarantine.append(
                {
                    "source_row_number": row_number,
                    "query_id": str(raw.get("query_id", "")),
                    "configuration": str(raw.get("configuration", "")),
                    "reasons": sorted(set(reasons)),
                    "record": raw,
                }
            )
            events.extend(
                {
                    "row_number": row_number,
                    "query_id": str(raw.get("query_id", "")),
                    "level": "error",
                    "code": reason,
                }
                for reason in reasons
            )
            continue
        value = dict(raw)
        value["preprocessing"] = {
            "version": PREPROCESSING_VERSION,
            "source_row_number": row_number,
            "analysis_eligible": raw.get("status") == "ok",
            "outlier_flags": [],
        }
        accepted.append(value)

    _flag_resource_outliers(
        accepted,
        threshold=robust_z_threshold,
        events=events,
    )
    metric_missing = Counter()
    outlier_counts = Counter()
    for row in accepted:
        telemetry = row.get("telemetry", {})
        if row.get("status") == "ok":
            for name, value in (
                ("energy_j", telemetry.get("energy_j")),
                ("process_peak_rss_mb", telemetry.get("process_peak_rss_mb")),
                ("temperature_c_peak", telemetry.get("temperature_c_peak")),
            ):
                if _finite_nonnegative(value) is None:
                    metric_missing[name] += 1
        for flag in row["preprocessing"]["outlier_flags"]:
            outlier_counts[flag] += 1

    report = {
        "schema_version": "1.0",
        "preprocessing_version": PREPROCESSING_VERSION,
        "parameters": {
            "require_energy": require_energy,
            "robust_z_threshold": robust_z_threshold,
            "outlier_action": "flag_only",
        },
        "counts": {
            "input_rows": len(input_rows),
            "output_rows": len(accepted),
            "analysis_eligible_rows": sum(
                row["preprocessing"]["analysis_eligible"] for row in accepted
            ),
            "quarantined_rows": len(quarantine),
        },
        "missing_metrics": dict(sorted(metric_missing.items())),
        "outlier_flags": dict(sorted(outlier_counts.items())),
        "quality_gates": {
            "outliers_not_silently_deleted": True,
            "failed_runs_preserved": True,
            "physical_energy_required": require_energy,
        },
    }
    return PreprocessResult(accepted, quarantine, events, report)


def _flag_resource_outliers(
    rows: list[dict[str, Any]],
    *,
    threshold: float,
    events: list[dict[str, Any]],
) -> None:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("status") == "ok":
            grouped[str(row["configuration"])].append(row)
    metrics = (
        ("latency_ms", lambda row: row.get("latency_ms")),
        ("energy_j", lambda row: row.get("telemetry", {}).get("energy_j")),
        (
            "process_peak_rss_mb",
            lambda row: row.get("telemetry", {}).get("process_peak_rss_mb"),
        ),
        (
            "temperature_c_peak",
            lambda row: row.get("telemetry", {}).get("temperature_c_peak"),
        ),
    )
    for configuration, samples in grouped.items():
        for metric_name, getter in metrics:
            valid: list[tuple[dict[str, Any], float]] = []
            for row in samples:
                value = _finite_nonnegative(getter(row))
                if value is not None:
                    valid.append((row, value))
            if len(valid) < 5:
                continue
            values = [value for _, value in valid]
            median = statistics.median(values)
            mad = statistics.median(abs(value - median) for value in values)
            if mad <= 0:
                continue
            for row, value in valid:
                robust_z = 0.67448975 * (value - median) / mad
                if abs(robust_z) <= threshold:
                    continue
                flag = f"{metric_name}:robust_z"
                row["preprocessing"]["outlier_flags"].append(flag)
                events.append(
                    {
                        "row_number": row["preprocessing"]["source_row_number"],
                        "query_id": str(row.get("query_id", "")),
                        "configuration": configuration,
                        "level": "warning",
                        "code": flag,
                        "value": value,
                        "median": median,
                        "mad": mad,
                        "robust_z": robust_z,
                    }
                )


def _finite_positive(value: Any) -> float | None:
    result = _as_finite_float(value)
    return result if result is not None and result > 0 else None


def _finite_nonnegative(value: Any) -> float | None:
    result = _as_finite_float(value)
    return result if result is not None and result >= 0 else None


def _as_finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None
