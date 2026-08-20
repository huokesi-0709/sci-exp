from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REQUIRED = {
    "schema_version",
    "external_query_id",
    "source_dataset",
    "source_record_id",
    "text",
    "language",
    "naturalness_class",
    "event_id",
    "disaster_type",
    "split_role",
    "license_id",
    "redistribution_scope",
    "noise_flags",
    "ambiguity_flags",
    "vulnerability_flags",
}
ROLES = {"external_adaptation", "external_sealed_test", "audit_only"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计外部查询组成、模板集中度与泄漏")
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-source-share", type=float, default=0.60)
    parser.add_argument("--max-template-share", type=float, default=0.20)
    return parser.parse_args()


def read_jsonl(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"{path}:{line_number} must be an object")
                value["_input_file"] = str(path)
                value["_line_number"] = line_number
                rows.append(value)
    return rows


def normalized_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.lower(), flags=re.UNICODE)


def template_signature(row: dict[str, Any]) -> str:
    explicit = str(row.get("template_id") or "").strip()
    if explicit:
        return explicit
    text = str(row.get("text", "")).lower()
    text = re.sub(r"https?://\S+|@\w+|#\w+", "<实体>", text)
    text = re.sub(r"\d+(?:\.\d+)?", "<数值>", text)
    text = re.sub(r"[\W_]+", "", text, flags=re.UNICODE)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def role_leakage(rows: list[dict[str, Any]], key_fn) -> list[dict[str, object]]:
    roles: dict[str, set[str]] = defaultdict(set)
    ids: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        key = key_fn(row)
        if not key:
            continue
        roles[key].add(str(row.get("split_role", "")))
        ids[key].append(str(row.get("external_query_id", "")))
    return [
        {"key": key, "roles": sorted(role_set), "external_query_ids": ids[key]}
        for key, role_set in sorted(roles.items())
        if "external_adaptation" in role_set and "external_sealed_test" in role_set
    ]


def main() -> int:
    args = parse_args()
    rows = read_jsonl(args.inputs)
    errors: list[dict[str, object]] = []
    for row in rows:
        missing = sorted(REQUIRED - row.keys())
        if missing:
            errors.append(
                {
                    "external_query_id": row.get("external_query_id"),
                    "error": "missing_required_fields",
                    "fields": missing,
                }
            )
        if row.get("schema_version") != "external-query-v1.0":
            errors.append(
                {
                    "external_query_id": row.get("external_query_id"),
                    "error": "wrong_schema_version",
                }
            )
        if row.get("split_role") not in ROLES:
            errors.append(
                {
                    "external_query_id": row.get("external_query_id"),
                    "error": "invalid_split_role",
                }
            )

    source_counts = Counter(str(row.get("source_dataset", "")) for row in rows)
    role_counts = Counter(str(row.get("split_role", "")) for row in rows)
    naturalness = Counter(str(row.get("naturalness_class", "")) for row in rows)
    disasters = Counter(str(row.get("disaster_type", "")) for row in rows)
    templates = Counter(template_signature(row) for row in rows)
    denominator = max(len(rows), 1)
    max_source_share = max(source_counts.values(), default=0) / denominator
    max_template_share = max(templates.values(), default=0) / denominator

    leakages = {
        "source_record": role_leakage(
            rows, lambda row: f"{row.get('source_dataset')}|{row.get('source_record_id')}"
        ),
        "event": role_leakage(rows, lambda row: str(row.get("event_id", ""))),
        "perturbation_parent": role_leakage(
            rows, lambda row: str(row.get("perturbation_parent_id") or "")
        ),
        "normalized_text": role_leakage(
            rows, lambda row: normalized_text(str(row.get("text", "")))
        ),
    }
    leakage_count = sum(len(values) for values in leakages.values())
    gates = {
        "schema_valid": not errors,
        "no_adaptation_test_leakage": leakage_count == 0,
        "source_concentration_ok": max_source_share <= args.max_source_share,
        "template_concentration_ok": max_template_share <= args.max_template_share,
        "sealed_test_present": role_counts["external_sealed_test"] > 0,
        "adaptation_set_present": role_counts["external_adaptation"] > 0,
        "natural_or_quasi_natural_present": (
            naturalness["natural_public_post"] + naturalness["quasi_natural_report"]
        ) > 0,
    }
    report = {
        "schema_version": "external-audit-v1.0",
        "inputs": [str(path) for path in args.inputs],
        "row_count": len(rows),
        "counts": {
            "source_dataset": dict(source_counts),
            "split_role": dict(role_counts),
            "naturalness_class": dict(naturalness),
            "disaster_type": dict(disasters),
        },
        "concentration": {
            "maximum_source_share": max_source_share,
            "maximum_template_share": max_template_share,
            "source_threshold": args.max_source_share,
            "template_threshold": args.max_template_share,
            "top_templates": templates.most_common(20),
        },
        "leakages": leakages,
        "validation_errors": errors,
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "interpretation": (
            "自然分布与挑战分布必须分别报告；公开数据的原标签不能直接作为"
            "协议安全答案标签。"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(args.output), **gates}, ensure_ascii=False))
    return 0 if report["all_gates_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
