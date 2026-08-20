from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从24条仲裁结果生成仅供先导分析的查询数据集。"
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--manifest", required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    manifest_path = Path(args.manifest).resolve()
    source_rows = [
        json.loads(line)
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    rows: list[dict[str, Any]] = []
    for source in source_rows:
        rows.append(
            {
                "query_id": source["query_id"],
                "text": source["text"],
                "disaster_type": source["disaster_type"],
                "query_type": source["query_type"],
                "risk_level": source["risk_level"],
                "language": source["language"],
                "should_fallback": source["should_fallback"],
                "gold_evidence_ids": source["gold_evidence_ids"],
                "required_actions": source["required_actions"],
                "prohibited_actions": source["prohibited_actions"],
                "source_group_id": source["source_group_id"],
                "split": "",
                "annotation_status": source["annotation_status"],
                "annotation_version": source["annotation_version"],
                "evidence_binding_status": source["evidence_binding_status"],
                "pilot_status": source["pilot_status"],
                "formal_training_eligible": False,
                "data_status": "pilot_only_not_formal_dataset",
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
        "manifest_version": "pilot-query-v0.1",
        "record_count": len(rows),
        "source_file": str(input_path),
        "source_sha256": sha256(input_path),
        "output_file": str(output_path),
        "output_sha256": sha256(output_path),
        "formal_training_eligible": False,
        "split_frozen": False,
        "status": "pilot_only_not_formal_dataset",
        "excluded_fields": [
            "machine_candidate_evidence",
            "review_record",
            "legacy_source",
        ],
        "limitations": [
            "协议来源许可和版本尚未全部冻结",
            "样本量仅24条，不能支撑正式功效分析",
            "split为空，不得用于训练、校准或正式测试",
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
                "record_count": len(rows),
                "formal_training_eligible": False,
                "output": str(output_path),
                "manifest": str(manifest_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
