from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MENTION = re.compile(r"(?<!\w)@\w+")
EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d .()/-]{6,}\d)(?!\d)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入并脱敏CrisisNLP真实请求/供给")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args()


def redact(text: str) -> tuple[str, list[str]]:
    flags: list[str] = []
    replacements = [
        (EMAIL, "[邮箱]", "email"),
        (URL, "[链接]", "url"),
        (MENTION, "[用户]", "user_mention"),
        (PHONE, "[电话]", "phone"),
    ]
    result = text
    for pattern, replacement, flag in replacements:
        if pattern.search(result):
            flags.append(flag)
            result = pattern.sub(replacement, result)
    return re.sub(r"\s+", " ", result).strip(), flags


def list_value(classification: dict[str, Any], key: str) -> list[str]:
    value = classification.get(key, [])
    return [str(item) for item in value] if isinstance(value, list) else []


def infer_flags(
    text: str, classification: dict[str, Any]
) -> tuple[list[str], list[str], list[str]]:
    lower = text.lower()
    noise: list[str] = []
    if lower.startswith("rt "):
        noise.append("retweet_marker")
    if "#" in text:
        noise.append("hashtag")
    if "..." in text or "…" in text:
        noise.append("truncated_or_ellipsis")
    if re.search(r"\b(?:frm|pls|plz|u|ur)\b", lower):
        noise.append("informal_abbreviation")
    ambiguity: list[str] = []
    if not classification.get("location"):
        ambiguity.append("missing_location")
    if not classification.get("time"):
        ambiguity.append("missing_time")
    types = list_value(classification, "type")
    if len(types) > 1:
        ambiguity.append("request_offer_overlap")
    if not bool(classification.get("actionability")):
        ambiguity.append("low_actionability")
    vulnerable_terms = {
        "children": ("child", "children", "kid", "baby", "infant", "diaper"),
        "older_adult": ("elderly", "older adult", "senior"),
        "homeless": ("homeless",),
        "disabled": ("disabled", "disability", "wheelchair"),
        "animal": ("pet", "dog", "cat", "animal"),
    }
    vulnerability = [
        group
        for group, terms in vulnerable_terms.items()
        if any(term in lower for term in terms)
    ]
    return sorted(set(noise)), sorted(set(ambiguity)), vulnerability


def main() -> int:
    args = parse_args()
    values = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(values, list):
        raise ValueError("input root must be a JSON array")
    rows: list[dict[str, Any]] = []
    redacted_count = 0
    for index, value in enumerate(values, 1):
        if not isinstance(value, dict):
            raise ValueError(f"row {index} is not an object")
        original = str(value.get("text", "")).strip()
        classification = value.get("classification", {})
        if not isinstance(classification, dict):
            classification = {}
        text, privacy_flags = redact(original)
        noise, ambiguity, vulnerability = infer_flags(original, classification)
        noise = sorted(set(noise + privacy_flags))
        if privacy_flags:
            redacted_count += 1
        digest = hashlib.sha256(original.encode("utf-8")).hexdigest()
        sandy = "sandy" in original.lower() or "nyc" in original.lower()
        event_id = "hurricane_sandy_2012" if sandy else "hurricane_sandy_context_uncertain"
        need_types = sorted(
            set(
                list_value(classification, "action_request")
                + list_value(classification, "personnel_request")
                + list_value(classification, "supplies_request")
                + list_value(classification, "action_offer")
                + list_value(classification, "personnel_offer")
                + list_value(classification, "supplies_offer")
            )
        )
        rows.append(
            {
                "schema_version": "external-query-v1.0",
                "external_query_id": f"crisis_ro_real_{index:04d}",
                "source_dataset": "CRISIS_REQUESTS_OFFERS",
                "source_record_id": digest,
                "text": text,
                "language": "en",
                "source_modality": "social_media_post",
                "naturalness_class": "natural_public_post",
                "event_id": event_id,
                "event_date": "2012-10/2012-11",
                "jurisdiction": "US-NY-NJ",
                "disaster_type": "hurricane",
                "need_type": need_types,
                "original_label": classification,
                "split_role": "external_adaptation",
                "seal_status": "open_development",
                "license_id": "CC-BY-NC-SA-4.0",
                "redistribution_scope": "public_text_allowed",
                "contains_personal_data": bool(privacy_flags),
                "privacy_action": (
                    "redact_before_use" if privacy_flags else "none"
                ),
                "noise_flags": noise,
                "ambiguity_flags": ambiguity,
                "vulnerability_flags": vulnerability,
                "perturbation_parent_id": None,
                "perturbation_type": None,
                "template_id": None,
                "protocol_answer_annotation_status": "not_started",
                "derivation": {
                    "script": "导入CrisisNLP真实请求供给.py",
                    "original_text_sha256": digest,
                    "event_assignment": (
                        "explicit_sandy_or_nyc_marker"
                        if sandy
                        else "dataset_context_requires_manual_confirmation"
                    ),
                },
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    uncertain_count = sum(
        row["event_id"] == "hurricane_sandy_context_uncertain" for row in rows
    )
    report = {
        "schema_version": "crisis-requests-offers-import-v1.0",
        "input": str(args.input),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "output": str(args.output),
        "record_count": len(rows),
        "redacted_record_count": redacted_count,
        "events": {
            event: sum(row["event_id"] == event for row in rows)
            for event in sorted({row["event_id"] for row in rows})
        },
        "split_role": "external_adaptation",
        "not_a_safety_answer_dataset": True,
        "manual_tasks": [
            f"复核{uncertain_count}条没有明确Sandy/NYC标记的记录是否仍属于Sandy事件",
            "对需转化为RAG输入的记录重新绑定中文适用协议",
            "不得把原classification直接当作安全答案或路由gold标签"
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
