from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


NAVIGATION_MARKERS = (
    "首页",
    "机构",
    "相关链接",
    "责任编辑",
    "打印",
    "字体",
)
MANUAL_SCOPE_REVIEW_TERMS = (
    "尿液",
    "掐人中",
    "按压人中",
    "酒精擦浴",
    "藿香正气",
    "环甲膜",
    "胸腔",
    "气管插管",
    "止血带",
)


def has_navigation_marker(text: str, marker: str) -> bool:
    lines = (line.strip() for line in text.splitlines())
    return any(
        line == marker
        or line.startswith(f"{marker}：")
        or line.startswith(f"{marker}:")
        for line in lines
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
    return rows


def audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("source_id", ""))].append(row)

    source_results: dict[str, Any] = {}
    for source_id, source_rows in sorted(grouped.items()):
        texts = [str(row.get("text", "")) for row in source_rows]
        term_hits = {
            term: [
                str(row.get("evidence_id", ""))
                for row in source_rows
                if term in str(row.get("text", ""))
            ]
            for term in MANUAL_SCOPE_REVIEW_TERMS
        }
        term_hits = {key: value for key, value in term_hits.items() if value}
        source_results[source_id] = {
            "title": str(source_rows[0].get("title", "")),
            "chunks": len(source_rows),
            "characters_with_overlap": sum(len(text) for text in texts),
            "minimum_chunk_characters": min(map(len, texts), default=0),
            "maximum_chunk_characters": max(map(len, texts), default=0),
            "replacement_characters": sum(text.count("�") for text in texts),
            "navigation_marker_chunks": {
                marker: sum(
                    has_navigation_marker(text, marker) for text in texts
                )
                for marker in NAVIGATION_MARKERS
            },
            "manual_scope_review_hits": term_hits,
            "statuses": dict(
                Counter(str(row.get("status", "")) for row in source_rows)
            ),
            "content_review_statuses": sorted(
                {str(row.get("content_review_status", "")) for row in source_rows}
            ),
            "license_statuses": sorted(
                {str(row.get("license_status", "")) for row in source_rows}
            ),
            "redistribution_statuses": sorted(
                {str(row.get("redistribution_status", "")) for row in source_rows}
            ),
            "file_sha256_values": sorted(
                {str(row.get("file_sha256", "")) for row in source_rows}
            ),
        }

    evidence_ids = [str(row.get("evidence_id", "")) for row in rows]
    eligibility_failures: list[str] = []
    if any(str(row.get("status", "")) != "current" for row in rows):
        eligibility_failures.append("not_all_chunks_are_current")
    if any(
        str(row.get("content_review_status", "")) != "approved"
        for row in rows
    ):
        eligibility_failures.append("content_review_not_approved")
    if any(
        str(row.get("license_status", "")) != "confirmed"
        for row in rows
    ):
        eligibility_failures.append("license_not_confirmed")
    if any("�" in str(row.get("text", "")) for row in rows):
        eligibility_failures.append("replacement_characters_present")
    if any(not str(row.get("source_id", "")) for row in rows):
        eligibility_failures.append("missing_source_id")
    if any(not str(row.get("file_sha256", "")) for row in rows):
        eligibility_failures.append("missing_file_sha256")
    if len(evidence_ids) != len(set(evidence_ids)):
        eligibility_failures.append("duplicate_evidence_id")

    return {
        "rows": len(rows),
        "sources": len(grouped),
        "unique_evidence_ids": len(set(evidence_ids)),
        "formal_knowledge_base_eligible": not eligibility_failures,
        "eligibility_failures": eligibility_failures,
        "source_results": source_results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计候选协议切块的来源和文本风险。")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    report = audit(read_jsonl(input_path))
    report.update(
        {
            "schema_version": "1.0",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "input": {
                "path": str(input_path),
                "sha256": sha256_file(input_path),
            },
        }
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "sources": report["sources"],
                "rows": report["rows"],
                "formal_knowledge_base_eligible": report[
                    "formal_knowledge_base_eligible"
                ],
                "eligibility_failures": report["eligibility_failures"],
                "output": str(output_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
