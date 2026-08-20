from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从120条历史候选中排除24条先导样本，生成待重新标注扩展池。"
    )
    parser.add_argument("--candidate-input", required=True)
    parser.add_argument("--pilot-input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    candidate_path = Path(args.candidate_input).resolve()
    pilot_path = Path(args.pilot_input).resolve()
    output_path = Path(args.output).resolve()
    manifest_path = Path(args.manifest).resolve()
    candidates = read_jsonl(candidate_path)
    pilot_ids = {row["query_id"] for row in read_jsonl(pilot_path)}
    remaining = [row for row in candidates if row["query_id"] not in pilot_ids]

    rows: list[dict[str, Any]] = []
    for row in remaining:
        legacy = row.get("legacy_source", {})
        rows.append(
            {
                "query_id": row["query_id"],
                "text": row["text"],
                "language": row.get("language", ""),
                "legacy_hint": {
                    "disaster_type": row.get("disaster_type", ""),
                    "query_type": row.get("query_type", ""),
                    "risk_level": row.get("risk_level"),
                    "should_fallback": row.get("should_fallback"),
                    "source_group_id": row.get("source_group_id", ""),
                    "legacy_primary_intent": legacy.get(
                        "legacy_primary_intent", ""
                    ),
                    "legacy_perturbation_types": legacy.get(
                        "legacy_perturbation_types", []
                    ),
                },
                "reannotation_requirements": row.get(
                    "current_reannotation_requirements", []
                ),
                "gold_evidence_ids": [],
                "required_actions": [],
                "prohibited_actions": [],
                "split": "",
                "candidate_status": "expansion_candidate_pending_reannotation",
                "legacy_labels_not_gold": True,
                "formal_training_eligible": False,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )
    manifest = {
        "manifest_version": "pilot-expansion-candidates-v0.1",
        "candidate_input": str(candidate_path),
        "candidate_input_sha256": sha256(candidate_path),
        "pilot_input": str(pilot_path),
        "pilot_input_sha256": sha256(pilot_path),
        "candidate_count": len(candidates),
        "excluded_pilot_count": len(pilot_ids),
        "expansion_candidate_count": len(rows),
        "output": str(output_path),
        "output_sha256": sha256(output_path),
        "formal_training_eligible": False,
        "split_frozen": False,
        "legacy_labels_not_gold": True,
        "legacy_hint_distributions": {
            "disaster_type": dict(
                Counter(
                    str(row["legacy_hint"]["disaster_type"]) for row in rows
                )
            ),
            "query_type": dict(
                Counter(str(row["legacy_hint"]["query_type"]) for row in rows)
            ),
            "risk_level": dict(
                Counter(str(row["legacy_hint"]["risk_level"]) for row in rows)
            ),
        },
        "required_next_actions": [
            "逐条独立复核灾种、查询类型、风险等级和回退标签",
            "重新绑定当前已批准协议证据，不继承legacy gold_evidence_ids",
            "补齐必需行动、禁止行动和source_group_id",
            "完成双人标注和专家仲裁后才能进入正式候选集",
        ],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "candidate_count": len(candidates),
                "excluded_pilot_count": len(pilot_ids),
                "expansion_candidate_count": len(rows),
                "output": str(output_path),
                "manifest": str(manifest_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
