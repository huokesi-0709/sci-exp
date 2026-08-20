from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_QUOTAS = {
    "clean_control": 36,
    "negation_conflict": 35,
    "multi_intent": 45,
    "out_of_scope": 4,
}

RISK_LEVEL_MAP = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "critical": 3,
}

DISASTER_TYPE_MAP = {
    "aftershock_or_collapse_hazard": "earthquake_building_safety",
    "trapped_or_entrapment": "earthquake_building_safety",
    "crush_injury": "earthquake_building_safety",
    "respiratory_distress": "cross_disaster_health",
    "severe_bleeding_or_shock": "injury_first_aid",
    "trauma_or_fracture": "injury_first_aid",
    "altered_consciousness_or_head_injury": "injury_first_aid",
    "hypothermia": "extreme_weather_exposure",
    "dehydration_or_resource_deprivation": "extreme_weather_exposure",
    "psychological_distress": "cross_disaster_support",
    "low_battery": "operational_constraint",
    "out_of_scope": "general",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Import a deterministic, provenance-preserving pilot candidate "
            "pool from the legacy monibox RAIR-RAG gold data."
        )
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--annotation-template", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-per-canonical", type=int, default=2)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: row must be an object")
            rows.append(value)
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_rank(seed: int, row_id: str) -> str:
    return hashlib.sha256(f"{seed}:{row_id}".encode("utf-8")).hexdigest()


def primary_perturbation(row: dict[str, Any]) -> str:
    values = {str(value) for value in row.get("perturbation_types", [])}
    if "out_of_scope" in values:
        return "out_of_scope"
    if "negation_conflict" in values:
        return "negation_conflict"
    if "multi_intent" in values:
        return "multi_intent"
    if "clean_control" in values:
        return "clean_control"
    raise ValueError(
        f"legacy row {row.get('id', '<unknown>')} has no supported perturbation"
    )


def select_balanced(
    rows: list[dict[str, Any]],
    *,
    seed: int,
    max_per_canonical: int,
) -> list[dict[str, Any]]:
    by_type_and_intent: dict[
        str, dict[str, list[dict[str, Any]]]
    ] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        perturbation = primary_perturbation(row)
        intent = str(row.get("primary_intent", "unknown"))
        by_type_and_intent[perturbation][intent].append(row)
    for intent_groups in by_type_and_intent.values():
        for intent, values in intent_groups.items():
            values.sort(
                key=lambda row: stable_rank(
                    seed,
                    f"{intent}:{row.get('id', '')}",
                )
            )

    selected: list[dict[str, Any]] = []
    canonical_counts: Counter[str] = Counter()
    for perturbation, quota in DEFAULT_QUOTAS.items():
        groups = by_type_and_intent[perturbation]
        intents = sorted(groups)
        positions = {intent: 0 for intent in intents}
        chosen = 0
        while chosen < quota:
            made_progress = False
            for intent in intents:
                values = groups[intent]
                while positions[intent] < len(values):
                    row = values[positions[intent]]
                    positions[intent] += 1
                    canonical_id = str(row["canonical_id"])
                    if canonical_counts[canonical_id] >= max_per_canonical:
                        continue
                    selected.append(row)
                    canonical_counts[canonical_id] += 1
                    chosen += 1
                    made_progress = True
                    break
                if chosen >= quota:
                    break
            if not made_progress:
                raise ValueError(
                    f"cannot satisfy quota {quota} for {perturbation} "
                    f"with max_per_canonical={max_per_canonical}"
                )
    selected.sort(key=lambda row: str(row["id"]))
    return selected


def convert_row(row: dict[str, Any]) -> dict[str, Any]:
    perturbation = primary_perturbation(row)
    legacy_intent = str(row.get("primary_intent", "unknown"))
    legacy_risk = str(row.get("risk_level", ""))
    if legacy_risk not in RISK_LEVEL_MAP:
        raise ValueError(f"unsupported legacy risk level: {legacy_risk}")
    legacy_protocol = row.get("expected_protocol_id")
    should_fallback = (
        legacy_intent == "out_of_scope" or legacy_protocol in (None, "")
    )
    return {
        "query_id": f"pilot_legacy_{row['id']}",
        "text": str(row["raw_input"]).strip(),
        "disaster_type": DISASTER_TYPE_MAP.get(
            legacy_intent,
            "legacy_unmapped",
        ),
        "query_type": perturbation,
        "risk_level": RISK_LEVEL_MAP[legacy_risk],
        "language": str(row.get("language", "zh-CN")),
        "should_fallback": should_fallback,
        "gold_evidence_ids": [],
        "required_actions": [],
        "prohibited_actions": [],
        "source_group_id": f"legacy_rair:{row['canonical_id']}",
        "split": "",
        "pilot_status": "needs_protocol_grounding_and_current_reannotation",
        "formal_training_eligible": False,
        "source_type": "legacy_monibox_rair_gold_v2_candidate",
        "legacy_source": {
            "project": "D:/projects/monibox-Y/monibox",
            "dataset": "RAIR-RAG-Bench",
            "legacy_id": row["id"],
            "legacy_canonical_id": row["canonical_id"],
            "legacy_label_status": row.get("label_status"),
            "legacy_risk_level": legacy_risk,
            "legacy_primary_intent": legacy_intent,
            "legacy_secondary_intents": row.get("secondary_intents", []),
            "legacy_negated_risks": row.get("negated_risks", []),
            "legacy_operational_constraints": row.get(
                "operational_constraints",
                [],
            ),
            "legacy_expected_route": row.get("expected_route"),
            "legacy_expected_protocol_id": legacy_protocol,
            "legacy_guideline_refs": row.get("guideline_refs", []),
            "legacy_perturbation_types": row.get(
                "perturbation_types",
                [],
            ),
        },
        "current_reannotation_requirements": [
            "confirm_disaster_type",
            "confirm_query_type",
            "confirm_risk_level_L0_to_L3",
            "confirm_should_fallback",
            "link_current_protocol_evidence_ids",
            "label_required_actions",
            "label_prohibited_actions",
            "confirm_source_group_id",
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            handle.write("\n")


def write_annotation_template(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "query_id",
        "text",
        "annotator_id",
        "keep_for_pilot",
        "disaster_type_final",
        "query_type_final",
        "risk_level_final",
        "should_fallback_final",
        "gold_evidence_ids_final",
        "required_actions_final",
        "prohibited_actions_final",
        "source_group_id_final",
        "decision_status",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "query_id": row["query_id"],
                    "text": row["text"],
                    "annotator_id": "",
                    "keep_for_pilot": "",
                    "disaster_type_final": "",
                    "query_type_final": "",
                    "risk_level_final": "",
                    "should_fallback_final": "",
                    "gold_evidence_ids_final": "",
                    "required_actions_final": "",
                    "prohibited_actions_final": "",
                    "source_group_id_final": row["source_group_id"],
                    "decision_status": "unreviewed",
                    "notes": "",
                }
            )


def write_report(
    path: Path,
    *,
    input_path: Path,
    output_path: Path,
    annotation_path: Path,
    seed: int,
    max_per_canonical: int,
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    perturbations = Counter(str(row["query_type"]) for row in rows)
    intents = Counter(
        str(row["legacy_source"]["legacy_primary_intent"]) for row in rows
    )
    risks = Counter(str(row["risk_level"]) for row in rows)
    report = {
        "schema_version": "1.0",
        "purpose": "legacy_candidate_import_for_pilot_reannotation_only",
        "seed": seed,
        "max_per_canonical": max_per_canonical,
        "quotas": DEFAULT_QUOTAS,
        "input": {
            "path": str(input_path.resolve()),
            "sha256": sha256_file(input_path),
        },
        "outputs": {
            "candidate_jsonl": {
                "path": str(output_path.resolve()),
                "sha256": sha256_file(output_path),
            },
            "annotation_template_csv": {
                "path": str(annotation_path.resolve()),
                "sha256": sha256_file(annotation_path),
            },
        },
        "counts": {
            "rows": len(rows),
            "unique_query_ids": len({str(row["query_id"]) for row in rows}),
            "unique_source_groups": len(
                {str(row["source_group_id"]) for row in rows}
            ),
            "formal_training_eligible": sum(
                bool(row["formal_training_eligible"]) for row in rows
            ),
        },
        "distribution": {
            "query_type": dict(sorted(perturbations.items())),
            "risk_level": dict(sorted(risks.items())),
            "legacy_primary_intent": dict(sorted(intents.items())),
        },
        "limitations": [
            "All source rows are template-generated and human-reviewed legacy data.",
            "Legacy labels target pre-retrieval risk routing, not per-configuration RAG severe failure.",
            "Legacy expected_protocol_id is not a current gold evidence chunk ID.",
            "Some legacy Chinese guideline references were marked pending source confirmation.",
            "Every row requires current protocol grounding and independent reannotation.",
            "No imported row is eligible for formal training, calibration, or testing yet.",
        ],
    }
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    annotation_path = Path(args.annotation_template)
    report_path = Path(args.report)
    source_rows = read_jsonl(input_path)
    selected = select_balanced(
        source_rows,
        seed=args.seed,
        max_per_canonical=args.max_per_canonical,
    )
    converted = [convert_row(row) for row in selected]
    write_jsonl(output_path, converted)
    write_annotation_template(annotation_path, converted)
    write_report(
        report_path,
        input_path=input_path,
        output_path=output_path,
        annotation_path=annotation_path,
        seed=args.seed,
        max_per_canonical=args.max_per_canonical,
        rows=converted,
    )
    print(
        json.dumps(
            {
                "rows": len(converted),
                "output": str(output_path.resolve()),
                "annotation_template": str(annotation_path.resolve()),
                "report": str(report_path.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
