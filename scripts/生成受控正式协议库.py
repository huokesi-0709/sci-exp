from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成仅限内部非商业研究的正式协议切块库。")
    parser.add_argument("--input", required=True)
    parser.add_argument("--license-table", required=True)
    parser.add_argument("--freeze-report", required=True)
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
    input_path = Path(args.input).resolve()
    license_path = Path(args.license_table).resolve()
    freeze_path = Path(args.freeze_report).resolve()
    output_path = Path(args.output).resolve()
    manifest_path = Path(args.manifest).resolve()

    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze.get("formal_library_freeze") is not True:
        raise ValueError("正式协议库冻结门槛未通过")
    with license_path.open("r", encoding="utf-8-sig", newline="") as handle:
        licenses = {row["source_id"]: row for row in csv.DictReader(handle)}
    rows = read_jsonl(input_path)
    output: list[dict[str, Any]] = []
    for row in rows:
        parent = str(row["parent_source_id"])
        license_row = licenses.get(parent)
        if license_row is None:
            raise ValueError(f"缺少许可记录：{parent}")
        if license_row["内部正式实验资格"] != "true":
            raise ValueError(f"来源未取得内部实验资格：{parent}")
        disposition = license_row["正式库处置"]
        if disposition not in {
            "include_selected_excerpt_local_research_only",
            "include_official_document_with_attribution",
        }:
            continue
        value = dict(row)
        value.update(
            {
                "status": "current",
                "status_detail": "current_internal_research_v1.0",
                "content_review_status": "approved_for_internal_research",
                "license_status": license_row["使用依据类型"],
                "redistribution_status": (
                    "cleared_with_conditions"
                    if license_row["公开再分发资格"] == "true"
                    else "not_cleared"
                ),
                "formal_library_scope": (
                    "local_noncommercial_scientific_research_no_republication"
                ),
                "formal_library_version": "protocols-v1.0",
                "public_package_include_text": (
                    license_row["公开再分发资格"] == "true"
                ),
            }
        )
        output.append(value)

    if len(output) != len(rows):
        raise ValueError(
            f"精选切块出现不可纳入来源：input={len(rows)} output={len(output)}"
        )
    if len({row["evidence_id"] for row in output}) != len(output):
        raise ValueError("正式协议库存在重复evidence_id")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in output),
        encoding="utf-8",
        newline="\n",
    )
    source_counts: dict[str, int] = {}
    for row in output:
        parent = str(row["parent_source_id"])
        source_counts[parent] = source_counts.get(parent, 0) + 1
    manifest = {
        "manifest_version": "v1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "local_noncommercial_scientific_research_no_republication",
        "chunks": len(output),
        "sources": len(source_counts),
        "source_counts": dict(sorted(source_counts.items())),
        "input_sha256": sha256(input_path),
        "license_table_sha256": sha256(license_path),
        "freeze_report_sha256": sha256(freeze_path),
        "output_sha256": sha256(output_path),
        "public_redistribution_eligible": False,
        "quality_gates": {
            "all_sources_internal_research_eligible": True,
            "all_chunks_content_reviewed": True,
            "all_evidence_ids_unique": True,
            "public_package_must_filter_restricted_text": True,
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"chunks": len(output), "sources": len(source_counts), "output": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
