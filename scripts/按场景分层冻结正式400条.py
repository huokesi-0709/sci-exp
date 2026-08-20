from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SPLITS = ("train", "valid", "cal_op", "cal_ch", "test_op", "test_ch")
OP_SPLITS = ("train", "valid", "cal_op", "test_op")
TIME_CUTOFF = date(2026, 4, 1)
REGION_HOLDOUT = "CN-SX-JC"
NEAR_DUP_REVIEW_THRESHOLD = 0.88
NEAR_DUP_BLOCK_THRESHOLD = 0.94
VERSION = "v2.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按显式运营/挑战规则、来源组和近重复簇冻结400条开发查询。"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--protocols", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--combined-output", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--quality-report", required=True)
    parser.add_argument("--near-duplicate-report", required=True)
    parser.add_argument("--holdout-directory", required=True)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(character for character in text if character.isalnum())


def text_ngrams(text: str) -> Counter[str]:
    normalized = normalize_text(text)
    grams: Counter[str] = Counter()
    for size in (2, 3):
        if len(normalized) < size:
            continue
        grams.update(
            normalized[index : index + size]
            for index in range(len(normalized) - size + 1)
        )
    return grams


def cosine(left: Counter[str], right: Counter[str]) -> float:
    if not left or not right:
        return 0.0
    common = left.keys() & right.keys()
    numerator = sum(left[key] * right[key] for key in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


class UnionFind:
    def __init__(self, values: Iterable[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        root, child = sorted((left_root, right_root))
        self.parent[child] = root


def near_duplicate_pairs(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    vectors = {str(row["query_id"]): text_ngrams(str(row["text"])) for row in rows}
    normalized = {
        str(row["query_id"]): normalize_text(str(row["text"])) for row in rows
    }
    groups = {
        str(row["query_id"]): str(row["source_group_id"]) for row in rows
    }
    union = UnionFind(groups.values())
    review_pairs: list[dict[str, Any]] = []
    for index, left in enumerate(rows):
        left_id = str(left["query_id"])
        for right in rows[index + 1 :]:
            right_id = str(right["query_id"])
            if normalized[left_id] == normalized[right_id]:
                score = 1.0
                method = "normalized_exact"
            else:
                score = cosine(vectors[left_id], vectors[right_id])
                method = "character_2_3gram_cosine"
            if score < NEAR_DUP_REVIEW_THRESHOLD:
                continue
            cross_group = groups[left_id] != groups[right_id]
            blocking = cross_group and score >= NEAR_DUP_BLOCK_THRESHOLD
            if blocking:
                union.union(groups[left_id], groups[right_id])
            review_pairs.append(
                {
                    "query_id_left": left_id,
                    "query_id_right": right_id,
                    "source_group_left": groups[left_id],
                    "source_group_right": groups[right_id],
                    "similarity": round(score, 6),
                    "method": method,
                    "cross_source_group": cross_group,
                    "blocking_cluster_merge": blocking,
                    "review_decision": (
                        "auto_merge_partition_unit" if blocking else "review_only"
                    ),
                }
            )
    return review_pairs, {group: union.find(group) for group in groups.values()}


def parse_iso_date(raw: Any) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def source_family(source_id: str) -> str:
    return re.sub(r"_CURATED_V\d+$", "", source_id)


def normalized_action(action: str, strip_negation: bool = False) -> str:
    value = normalize_text(action)
    if strip_negation:
        for marker in ("不要", "不得", "禁止", "切勿", "避免", "不可", "停止"):
            value = value.replace(marker, "")
    return value


def action_conflicts(row: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    required = [str(value) for value in row.get("required_actions", [])]
    prohibited = [str(value) for value in row.get("prohibited_actions", [])]
    strict: list[str] = []
    candidates: list[dict[str, Any]] = []
    for required_action in required:
        for prohibited_action in prohibited:
            left = normalized_action(required_action)
            right = normalized_action(prohibited_action)
            if left and left == right:
                strict.append(required_action)
                continue
            left_base = normalized_action(required_action, strip_negation=True)
            right_base = normalized_action(prohibited_action, strip_negation=True)
            if not left_base or not right_base:
                continue
            grams_left = text_ngrams(left_base)
            grams_right = text_ngrams(right_base)
            score = cosine(grams_left, grams_right)
            containment = left_base in right_base or right_base in left_base
            if score >= 0.82 or (containment and min(len(left_base), len(right_base)) >= 4):
                candidates.append(
                    {
                        "query_id": row["query_id"],
                        "required_action": required_action,
                        "prohibited_action": prohibited_action,
                        "similarity": round(score, 6),
                        "containment": containment,
                    }
                )
    return sorted(set(strict)), candidates


def enrich_rows(
    rows: list[dict[str, Any]], protocols: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    evidence = {str(row["evidence_id"]): row for row in protocols}
    known_evidence = set(evidence)
    errors: dict[str, list[Any]] = defaultdict(list)
    action_review: list[dict[str, Any]] = []
    enriched: list[dict[str, Any]] = []
    for source in protocols:
        effective = parse_iso_date(source.get("effective_date"))
        if effective is None:
            errors["protocol_effective_date_unparseable"].append(source["evidence_id"])
        elif effective > date(2026, 7, 28):
            errors["protocol_effective_date_after_freeze"].append(source["evidence_id"])
        expiry_raw = source.get("expiry_date")
        if expiry_raw and parse_iso_date(expiry_raw) is None:
            errors["protocol_expiry_date_unparseable"].append(source["evidence_id"])
        if not str(source.get("jurisdiction", "")).strip():
            errors["protocol_jurisdiction_missing"].append(source["evidence_id"])

    for original in rows:
        row = dict(original)
        evidence_ids = [str(value) for value in row.get("gold_evidence_ids", [])]
        missing = sorted(set(evidence_ids) - known_evidence)
        if missing:
            errors["missing_evidence_ids"].append(
                {"query_id": row["query_id"], "evidence_ids": missing}
            )
        bound = [evidence[value] for value in evidence_ids if value in evidence]
        source_ids = sorted({str(item["source_id"]) for item in bound})
        jurisdictions = sorted({str(item["jurisdiction"]) for item in bound})
        effective_dates = sorted(
            {
                str(item["effective_date"])
                for item in bound
                if str(item.get("effective_date", "")).strip()
            }
        )
        versions = sorted(
            {
                str(item["version"])
                for item in bound
                if str(item.get("version", "")).strip()
            }
        )
        expected_families = {source_family(value) for value in source_ids}
        declared_family = str(row.get("protocol_family", ""))
        declared_families = (
            set(declared_family.split("+"))
            if declared_family and declared_family != "NONE"
            else set()
        )
        if expected_families != declared_families:
            errors["protocol_family_mismatch"].append(
                {
                    "query_id": row["query_id"],
                    "expected": sorted(expected_families),
                    "declared": sorted(declared_families),
                }
            )
        declared_version_chain = str(row.get("protocol_version_chain", ""))
        missing_versions = [
            version for version in versions if version not in declared_version_chain
        ]
        if missing_versions:
            errors["protocol_version_chain_mismatch"].append(
                {
                    "query_id": row["query_id"],
                    "missing_versions": missing_versions,
                }
            )
        strict_conflicts, candidate_conflicts = action_conflicts(row)
        if strict_conflicts:
            errors["strict_action_conflicts"].append(
                {"query_id": row["query_id"], "actions": strict_conflicts}
            )
        action_review.extend(candidate_conflicts)

        temporal_ood = "MEM_FLOOD_PREPAREDNESS_2026" in declared_families
        regional_ood = any(value == REGION_HOLDOUT for value in jurisdictions) or (
            "JINCHENG_HIGHRISE_FIRE_2026" in declared_families
        )
        out_of_scope = bool(row.get("expected_gap_control")) or (
            row.get("query_type") == "out_of_scope"
        )
        flags = []
        if temporal_ood:
            flags.append("temporal_ood_after_2026-04-01")
        if regional_ood:
            flags.append("regional_ood_CN-SX-JC")
        if out_of_scope:
            flags.append("out_of_scope")
        if row.get("query_type") == "negation_conflict":
            flags.append("negation_conflict")
        if row.get("query_type") == "multi_intent":
            flags.append("multi_intent")
        if int(row.get("risk_level", 0)) == 3:
            flags.append("L3")
        if bool(row.get("should_fallback")):
            flags.append("C3")

        row.update(
            {
                "split": "",
                "split_policy_version": "scenario-stratified-v2.0",
                "challenge_flags": flags,
                "temporal_ood": temporal_ood,
                "regional_ood": regional_ood,
                "version_ood": False,
                "evidence_source_ids": source_ids,
                "evidence_jurisdictions": jurisdictions,
                "evidence_effective_dates": effective_dates,
                "evidence_versions": versions,
            }
        )
        enriched.append(row)
    return enriched, {
        "errors": dict(errors),
        "action_conflict_review_candidates": action_review,
        "version_ood_constructible": False,
        "version_ood_reason": (
            "当前13个协议家族各只有一个纳入版本，无法构造同家族版本链外推测试；"
            "需要补入同一协议家族的前版或后续修订版。"
        ),
    }


def build_partition_units(
    rows: list[dict[str, Any]], group_roots: dict[str, str]
) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        root = group_roots[str(row["source_group_id"])]
        buckets[root].append(row)
    units: list[dict[str, Any]] = []
    for root, unit_rows in buckets.items():
        groups = sorted({str(row["source_group_id"]) for row in unit_rows})
        units.append(
            {
                "unit_id": "||".join(groups),
                "near_duplicate_root": root,
                "source_groups": groups,
                "rows": unit_rows,
                "n": len(unit_rows),
            }
        )
    return sorted(units, key=lambda value: value["unit_id"])


def unit_has(unit: dict[str, Any], field: str, value: Any = True) -> bool:
    return any(row.get(field) == value for row in unit["rows"])


def assign_challenge_units(
    units: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    assignments: dict[str, str] = {}
    reasons: dict[str, str] = {}
    mandatory_test = [
        unit
        for unit in units
        if unit_has(unit, "temporal_ood") or unit_has(unit, "regional_ood")
    ]
    for unit in mandatory_test:
        assignments[unit["unit_id"]] = "test_ch"
        reasons[unit["unit_id"]] = (
            "strict_temporal_or_regional_holdout; excluded from train/valid/cal_op/test_op"
        )

    out_units = [
        unit
        for unit in units
        if unit["unit_id"] not in assignments
        and unit_has(unit, "expected_gap_control")
    ]
    if out_units:
        test_out = sorted(out_units, key=lambda value: (-value["n"], value["unit_id"]))[0]
        assignments[test_out["unit_id"]] = "test_ch"
        reasons[test_out["unit_id"]] = "out_of_scope_test_ch_control"
    for unit in out_units:
        if unit["unit_id"] in assignments:
            continue
        assignments[unit["unit_id"]] = "cal_ch"
        reasons[unit["unit_id"]] = "out_of_scope_cal_ch_control"

    def ensure_cal_coverage(label: str, predicate: Any) -> None:
        if any(
            split == "cal_ch"
            and predicate(next(value for value in units if value["unit_id"] == unit_id))
            for unit_id, split in assignments.items()
        ):
            return
        candidates = [
            unit
            for unit in units
            if unit["unit_id"] not in assignments and predicate(unit)
        ]
        if not candidates:
            return
        chosen = sorted(candidates, key=lambda value: (value["n"], value["unit_id"]))[0]
        assignments[chosen["unit_id"]] = "cal_ch"
        reasons[chosen["unit_id"]] = f"cal_ch_explicit_{label}_coverage"

    ensure_cal_coverage(
        "L3", lambda unit: any(int(row["risk_level"]) == 3 for row in unit["rows"])
    )
    ensure_cal_coverage(
        "C3", lambda unit: any(bool(row["should_fallback"]) for row in unit["rows"])
    )
    ensure_cal_coverage(
        "negation",
        lambda unit: any(row["query_type"] == "negation_conflict" for row in unit["rows"]),
    )
    return assignments, reasons


def row_features(row: dict[str, Any]) -> set[str]:
    features = {
        f"disaster:{row['disaster_type']}",
        f"risk:L{row['risk_level']}",
        f"query_type:{row['query_type']}",
        f"fallback:{int(bool(row['should_fallback']))}",
    }
    features.update(f"source:{value}" for value in row.get("evidence_source_ids", []))
    return features


def row_category_features(row: dict[str, Any]) -> dict[str, set[str]]:
    return {
        "risk": {f"L{row['risk_level']}"},
        "fallback": {str(int(bool(row["should_fallback"])))},
        "query_type": {str(row["query_type"])},
        "disaster": {str(row["disaster_type"])},
        "source": set(row.get("evidence_source_ids", [])) or {"NONE"},
    }


def operational_targets(total: int) -> dict[str, int]:
    weights = {"train": 0.48, "valid": 0.12, "cal_op": 0.16, "test_op": 0.24}
    targets = {name: int(round(total * weight)) for name, weight in weights.items()}
    targets["train"] += total - sum(targets.values())
    return targets


def stratified_operational_assignment(
    units: list[dict[str, Any]], existing: dict[str, str]
) -> tuple[dict[str, str], dict[str, str], dict[str, int]]:
    assignments = dict(existing)
    reasons: dict[str, str] = {}
    remaining = [unit for unit in units if unit["unit_id"] not in assignments]
    total = sum(unit["n"] for unit in remaining)
    targets = operational_targets(total)
    categories = ("risk", "fallback", "query_type", "disaster", "source")
    category_weights = {
        "risk": 5.0,
        "fallback": 4.0,
        "query_type": 2.5,
        "disaster": 1.5,
        "source": 1.0,
    }
    global_categories = {category: Counter() for category in categories}
    for unit in remaining:
        for row in unit["rows"]:
            for category, values in row_category_features(row).items():
                global_categories[category].update(values)
    desired = {
        split: {
            category: {
                value: count * targets[split] / total
                for value, count in global_categories[category].items()
            }
            for category in categories
        }
        for split in OP_SPLITS
    }
    counts = {split: 0 for split in OP_SPLITS}
    feature_counts = {
        split: {category: Counter() for category in categories} for split in OP_SPLITS
    }

    def unit_categories(unit: dict[str, Any]) -> dict[str, Counter[str]]:
        unit_categories = {category: Counter() for category in categories}
        for row in unit["rows"]:
            for category, values in row_category_features(row).items():
                unit_categories[category].update(values)
        return unit_categories

    cached_categories = {
        unit["unit_id"]: unit_categories(unit) for unit in remaining
    }

    def commit(unit: dict[str, Any], split: str) -> None:
        assignments[unit["unit_id"]] = split
        reasons[unit["unit_id"]] = (
            "operational_groupwise_stratification_by_disaster_risk_query_type_"
            "fallback_and_evidence_source"
        )
        counts[split] += unit["n"]
        for category in categories:
            feature_counts[split][category].update(
                cached_categories[unit["unit_id"]][category]
            )

    unassigned = {unit["unit_id"]: unit for unit in remaining}

    def preassign_metric(
        label: str,
        metric: Any,
        metric_weight: float,
    ) -> None:
        candidates = [
            unit for unit in unassigned.values() if metric(unit) > 0
        ]
        total_metric = sum(metric(unit) for unit in candidates)
        metric_targets = {
            split: total_metric * targets[split] / total for split in OP_SPLITS
        }
        metric_counts = {split: 0 for split in OP_SPLITS}
        for unit in sorted(
            candidates, key=lambda value: (-metric(value), -value["n"], value["unit_id"])
        ):
            amount = metric(unit)
            options = []
            for split in OP_SPLITS:
                projected_metric_counts = dict(metric_counts)
                projected_metric_counts[split] += amount
                metric_error = sum(
                    (
                        (projected_metric_counts[name] - metric_targets[name])
                        / max(metric_targets[name], 1.0)
                    )
                    ** 2
                    for name in OP_SPLITS
                )
                projected_counts = dict(counts)
                projected_counts[split] += unit["n"]
                size_error = sum(
                    (
                        (projected_counts[name] - targets[name])
                        / max(targets[name], 1)
                    )
                    ** 2
                    for name in OP_SPLITS
                )
                overflow = sum(
                    max(0, projected_counts[name] - targets[name])
                    / max(targets[name], 1)
                    for name in OP_SPLITS
                )
                options.append(
                    (
                        metric_weight * metric_error
                        + 0.35 * size_error
                        + 3.0 * overflow,
                        split,
                    )
                )
            _, chosen = min(options, key=lambda value: (value[0], value[1]))
            commit(unit, chosen)
            reasons[unit["unit_id"]] += f"; explicit_{label}_quota"
            metric_counts[chosen] += amount
            del unassigned[unit["unit_id"]]

    preassign_metric(
        "L3",
        lambda unit: sum(
            int(row["risk_level"]) == 3 for row in unit["rows"]
        ),
        4.0,
    )
    preassign_metric(
        "C3",
        lambda unit: sum(bool(row["should_fallback"]) for row in unit["rows"]),
        3.0,
    )
    preassign_metric(
        "negation",
        lambda unit: sum(
            row["query_type"] == "negation_conflict" for row in unit["rows"]
        ),
        2.0,
    )

    for unit in sorted(
        unassigned.values(), key=lambda value: (-value["n"], value["unit_id"])
    ):
        categories_for_unit = cached_categories[unit["unit_id"]]
        candidates = []
        for split in OP_SPLITS:
            projected_n = counts[split] + unit["n"]
            size_error = abs(projected_n - targets[split]) / max(targets[split], 1)
            overflow = max(0, projected_n - targets[split]) / max(targets[split], 1)
            weighted_error = 0.0
            total_weight = 0.0
            for category in categories:
                category_error = 0.0
                for value, desired_count in desired[split][category].items():
                    projected = (
                        feature_counts[split][category][value]
                        + categories_for_unit[category][value]
                    )
                    category_error += abs(projected - desired_count) / max(
                        desired_count, 1.0
                    )
                category_error /= max(len(desired[split][category]), 1)
                weighted_error += category_weights[category] * category_error
                total_weight += category_weights[category]
            feature_error = weighted_error / total_weight
            empty_bonus = -0.4 if counts[split] == 0 else 0.0
            score = size_error + 1.2 * feature_error + 3.0 * overflow + empty_bonus
            candidates.append((score, split))
        _, chosen = min(candidates, key=lambda value: (value[0], value[1]))
        commit(unit, chosen)
    return assignments, reasons, targets


def split_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n": len(rows),
        "partition_units": len({row["partition_unit_id"] for row in rows}),
        "source_groups": len({row["source_group_id"] for row in rows}),
        "l3": sum(int(row["risk_level"]) == 3 for row in rows),
        "c3_fallback": sum(bool(row["should_fallback"]) for row in rows),
        "out_of_scope": sum(bool(row.get("expected_gap_control")) for row in rows),
        "temporal_ood": sum(bool(row.get("temporal_ood")) for row in rows),
        "regional_ood": sum(bool(row.get("regional_ood")) for row in rows),
        "negation_conflict": sum(
            row.get("query_type") == "negation_conflict" for row in rows
        ),
        "risk_distribution": dict(
            sorted(Counter(f"L{row['risk_level']}" for row in rows).items())
        ),
        "disaster_distribution": dict(
            sorted(Counter(str(row["disaster_type"]) for row in rows).items())
        ),
        "query_type_distribution": dict(
            sorted(Counter(str(row["query_type"]) for row in rows).items())
        ),
        "evidence_source_distribution": dict(
            sorted(
                Counter(
                    source
                    for row in rows
                    for source in row.get("evidence_source_ids", [])
                ).items()
            )
        ),
    }


def write_near_duplicate_report(path: Path, pairs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "query_id_left",
        "query_id_right",
        "source_group_left",
        "source_group_right",
        "similarity",
        "method",
        "cross_source_group",
        "blocking_cluster_merge",
        "review_decision",
    )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(pairs)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    protocols_path = Path(args.protocols).resolve()
    output_directory = Path(args.output_directory).resolve()
    combined_output = Path(args.combined_output).resolve()
    manifest_path = Path(args.manifest).resolve()
    quality_path = Path(args.quality_report).resolve()
    near_duplicate_path = Path(args.near_duplicate_report).resolve()
    holdout_directory = Path(args.holdout_directory).resolve()

    raw_rows = read_jsonl(input_path)
    protocols = read_jsonl(protocols_path)
    if len(raw_rows) != 400:
        raise ValueError(f"输入必须恰好400条，实际为{len(raw_rows)}")
    if len({str(row["query_id"]) for row in raw_rows}) != 400:
        raise ValueError("query_id不唯一")

    rows, audit = enrich_rows(raw_rows, protocols)
    near_pairs, group_roots = near_duplicate_pairs(rows)
    units = build_partition_units(rows, group_roots)
    challenge_assignments, challenge_reasons = assign_challenge_units(units)
    assignments, operational_reasons, targets = stratified_operational_assignment(
        units, challenge_assignments
    )
    reasons = {**challenge_reasons, **operational_reasons}

    by_split: dict[str, list[dict[str, Any]]] = {name: [] for name in SPLITS}
    for unit in units:
        split = assignments[unit["unit_id"]]
        for original in unit["rows"]:
            row = dict(original)
            row["split"] = split
            row["partition_unit_id"] = unit["unit_id"]
            row["split_assignment_reason"] = reasons[unit["unit_id"]]
            by_split[split].append(row)

    output_directory.mkdir(parents=True, exist_ok=True)
    split_hashes: dict[str, str] = {}
    for split in SPLITS:
        path = output_directory / f"{split}.jsonl"
        ordered = sorted(by_split[split], key=lambda value: str(value["query_id"]))
        write_jsonl(path, ordered)
        split_hashes[split] = sha256(path)

    combined_rows = [
        row
        for split in SPLITS
        for row in sorted(by_split[split], key=lambda value: str(value["query_id"]))
    ]
    write_jsonl(combined_output, combined_rows)
    write_near_duplicate_report(near_duplicate_path, near_pairs)

    temporal_rows = sorted(
        [row for row in by_split["test_ch"] if row.get("temporal_ood")],
        key=lambda value: str(value["query_id"]),
    )
    regional_rows = sorted(
        [row for row in by_split["test_ch"] if row.get("regional_ood")],
        key=lambda value: str(value["query_id"]),
    )
    write_jsonl(holdout_directory / "时间外测试_v2.0.jsonl", temporal_rows)
    write_jsonl(holdout_directory / "地区外测试_v2.0.jsonl", regional_rows)

    summaries = {split: split_summary(by_split[split]) for split in SPLITS}
    group_splits: dict[str, set[str]] = defaultdict(set)
    unit_splits: dict[str, set[str]] = defaultdict(set)
    for row in combined_rows:
        group_splits[str(row["source_group_id"])].add(str(row["split"]))
        unit_splits[str(row["partition_unit_id"])].add(str(row["split"]))
    cross_group_blocking_pairs = [
        pair for pair in near_pairs if pair["blocking_cluster_merge"]
    ]
    test_ch = summaries["test_ch"]
    cal_ch = summaries["cal_ch"]
    gates = {
        "exactly_400_rows": len(combined_rows) == 400,
        "all_normalized_query_texts_unique": len(
            {normalize_text(str(row["text"])) for row in combined_rows}
        )
        == 400,
        "at_least_40_independent_source_groups": len(group_splits) >= 40,
        "global_L3_C3_and_out_of_scope_quotas": (
            sum(int(row["risk_level"]) == 3 for row in combined_rows) >= 100
            and sum(bool(row["should_fallback"]) for row in combined_rows) >= 100
            and sum(bool(row.get("expected_gap_control")) for row in combined_rows)
            >= 30
        ),
        "all_six_splits_nonempty": all(by_split.values()),
        "source_group_no_leakage": all(len(value) == 1 for value in group_splits.values()),
        "near_duplicate_partition_unit_no_leakage": all(
            len(value) == 1 for value in unit_splits.values()
        ),
        "all_evidence_ids_exist": not audit["errors"].get("missing_evidence_ids"),
        "protocol_dates_parse_and_not_future": not (
            audit["errors"].get("protocol_effective_date_unparseable")
            or audit["errors"].get("protocol_effective_date_after_freeze")
            or audit["errors"].get("protocol_expiry_date_unparseable")
        ),
        "protocol_jurisdictions_present": not audit["errors"].get(
            "protocol_jurisdiction_missing"
        ),
        "protocol_family_and_version_chain_consistent": not (
            audit["errors"].get("protocol_family_mismatch")
            or audit["errors"].get("protocol_version_chain_mismatch")
        ),
        "no_strict_required_prohibited_action_conflicts": not audit["errors"].get(
            "strict_action_conflicts"
        ),
        "operational_eval_excludes_explicit_shift_controls": all(
            not row.get("temporal_ood")
            and not row.get("regional_ood")
            and not row.get("expected_gap_control")
            for split in ("cal_op", "test_op")
            for row in by_split[split]
        ),
        "operational_splits_each_cover_L3_and_C3": all(
            summaries[split]["l3"] > 0 and summaries[split]["c3_fallback"] > 0
            for split in OP_SPLITS
        ),
        "cal_ch_has_L3_C3_out_of_scope_and_negation": (
            cal_ch["l3"] > 0
            and cal_ch["c3_fallback"] > 0
            and cal_ch["out_of_scope"] > 0
            and cal_ch["negation_conflict"] > 0
        ),
        "test_ch_has_L3_C3_out_of_scope_time_and_region_shift": (
            test_ch["l3"] > 0
            and test_ch["c3_fallback"] > 0
            and test_ch["out_of_scope"] > 0
            and test_ch["temporal_ood"] > 0
            and test_ch["regional_ood"] > 0
        ),
        "temporal_holdout_only_in_test_ch": all(
            row["split"] == "test_ch" for row in combined_rows if row["temporal_ood"]
        ),
        "regional_holdout_only_in_test_ch": all(
            row["split"] == "test_ch" for row in combined_rows if row["regional_ood"]
        ),
        "augmentation_absent_outside_train": all(
            not row.get("augmentation_parent_id")
            for split in SPLITS
            if split != "train"
            for row in by_split[split]
        ),
        "all_adjudicated": all(
            row.get("annotation_status") in {"adjudicated", "quality_checked", "frozen"}
            for row in combined_rows
        ),
    }
    quality = {
        "report_version": VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "policy": {
            "method": "explicit_scenario_track_then_groupwise_multistratum_balancing",
            "time_cutoff_exclusive": TIME_CUTOFF.isoformat(),
            "temporal_holdout_family": "MEM_FLOOD_PREPAREDNESS_2026",
            "regional_holdout": REGION_HOLDOUT,
            "regional_holdout_family": "JINCHENG_HIGHRISE_FIRE_2026",
            "near_duplicate_review_threshold": NEAR_DUP_REVIEW_THRESHOLD,
            "near_duplicate_block_threshold": NEAR_DUP_BLOCK_THRESHOLD,
            "hash_used_for_assignment": False,
        },
        "input_rows": len(rows),
        "source_groups": len({row["source_group_id"] for row in rows}),
        "partition_units_after_near_duplicate_merge": len(units),
        "near_duplicate_review_pairs": len(near_pairs),
        "cross_group_blocking_pairs": len(cross_group_blocking_pairs),
        "operational_target_counts": targets,
        "split_summary": summaries,
        "audit": audit,
        "quality_gates": gates,
        "all_quality_gates_pass": all(gates.values()),
    }
    quality_path.parent.mkdir(parents=True, exist_ok=True)
    quality_path.write_text(
        json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not all(gates.values()):
        raise ValueError(f"分层冻结门槛未通过：{gates}")

    manifest = {
        "manifest_version": VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_role": "development_gold_not_confirmatory_3600",
        "method": "explicit_scenario_stratification_without_hash_assignment",
        "input": {
            "path": str(input_path),
            "sha256": sha256(input_path),
            "protocols_path": str(protocols_path),
            "protocols_sha256": sha256(protocols_path),
        },
        "policy": quality["policy"],
        "split_summary": summaries,
        "split_sha256": split_hashes,
        "combined_output": {
            "path": str(combined_output),
            "sha256": sha256(combined_output),
        },
        "holdouts": {
            "temporal": {
                "path": str(holdout_directory / "时间外测试_v2.0.jsonl"),
                "n": len(temporal_rows),
                "sha256": sha256(holdout_directory / "时间外测试_v2.0.jsonl"),
            },
            "regional": {
                "path": str(holdout_directory / "地区外测试_v2.0.jsonl"),
                "n": len(regional_rows),
                "sha256": sha256(holdout_directory / "地区外测试_v2.0.jsonl"),
            },
            "version": {
                "constructible": False,
                "reason": audit["version_ood_reason"],
            },
        },
        "near_duplicate_report": {
            "path": str(near_duplicate_path),
            "sha256": sha256(near_duplicate_path),
            "review_pairs": len(near_pairs),
            "blocking_cross_group_pairs": len(cross_group_blocking_pairs),
        },
        "quality_report": {
            "path": str(quality_path),
            "sha256": sha256(quality_path),
        },
        "quality_gates": gates,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "split_summary": summaries,
                "near_duplicate_review_pairs": len(near_pairs),
                "cross_group_blocking_pairs": len(cross_group_blocking_pairs),
                "quality_gates": gates,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
