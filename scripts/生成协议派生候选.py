from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sci_exp.ingestion import chunk_protocol_text  # noqa: E402


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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_units(
    source_path: Path,
    page_numbers: list[int],
    unit_trims: dict[str, dict[str, str]] | None = None,
) -> list[tuple[str, str, str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF派生需要pypdf") from exc
    reader = PdfReader(str(source_path))
    units: list[tuple[str, str, str]] = []
    for page_number in page_numbers:
        if page_number < 1 or page_number > len(reader.pages):
            raise ValueError(
                f"{source_path}: page {page_number} outside 1..{len(reader.pages)}"
            )
        text = normalize_text(reader.pages[page_number - 1].extract_text() or "")
        unit_id = f"p{page_number:03d}"
        trim = (unit_trims or {}).get(unit_id, {})
        start_marker = str(trim.get("start_marker", ""))
        end_marker = str(trim.get("end_marker", ""))
        if start_marker:
            start = text.find(start_marker)
            if start < 0:
                raise ValueError(
                    f"{source_path}: page {page_number} missing trim start "
                    f"marker {start_marker}"
                )
            text = text[start:]
        if end_marker:
            end = text.find(end_marker)
            if end < 0:
                raise ValueError(
                    f"{source_path}: page {page_number} missing trim end "
                    f"marker {end_marker}"
                )
            text = text[:end]
        if len(text) < 100:
            raise ValueError(
                f"{source_path}: page {page_number} extracted text too short"
            )
        units.append(
            (
                unit_id,
                f"原PDF页码：{page_number}",
                text,
            )
        )
    return units


def extract_text_units(
    source_path: Path,
    sections: list[dict[str, Any]],
) -> list[tuple[str, str, str]]:
    source_text = source_path.read_text(encoding="utf-8")
    units: list[tuple[str, str, str]] = []
    for section in sections:
        section_id = str(section["section_id"])
        start_marker = str(section["start_marker"])
        end_marker = str(section.get("end_marker", ""))
        start = source_text.find(start_marker)
        if start < 0:
            raise ValueError(f"{source_path}: missing start marker {start_marker}")
        if end_marker:
            end = source_text.find(end_marker, start + len(start_marker))
            if end < 0:
                raise ValueError(f"{source_path}: missing end marker {end_marker}")
        else:
            end = len(source_text)
        text = normalize_text(source_text[start:end])
        minimum_characters = int(section.get("min_characters", 100))
        if len(text) < minimum_characters:
            raise ValueError(
                f"{source_path}: section {section_id} too short "
                f"({len(text)} < {minimum_characters})"
            )
        units.append((section_id, f"网页章节：{section_id}", text))
    return units


def write_derived_markdown(
    path: Path,
    *,
    source: dict[str, Any],
    rule: dict[str, Any],
    units: list[tuple[str, str, str]],
) -> None:
    lines = [
        f"# {source['title']}：机器筛选派生候选",
        "",
        f"- parent_source_id: `{source['source_id']}`",
        f"- parent_file_sha256: `{source['file_sha256']}`",
        f"- source_url: {source['source_url']}",
        f"- derivation_review_status: `pending_double_review`",
        f"- 选择理由：{rule.get('reason', '')}",
        "",
        "> 本文件由确定性规则从官方本地副本派生，不是经专家批准的正式协议。",
        "",
    ]
    for unit_id, locator, text in units:
        lines.extend(
            [
                f"## {unit_id}",
                "",
                f"来源定位：{locator}",
                "",
                text,
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_chunks(
    source: dict[str, Any],
    rule: dict[str, Any],
    units: list[tuple[str, str, str]],
    *,
    derived_sha256: str,
    target_characters: int,
    overlap_characters: int,
) -> list[dict[str, Any]]:
    output_source_id = str(rule["output_source_id"])
    rows: list[dict[str, Any]] = []
    for unit_id, locator, text in units:
        unit_hazard_types = rule.get("unit_hazard_types", {}).get(
            unit_id,
            source["hazard_types"],
        )
        for index, chunk in enumerate(
            chunk_protocol_text(
                text,
                target_characters=target_characters,
                overlap_characters=overlap_characters,
            ),
            start=1,
        ):
            rows.append(
                {
                    "evidence_id": (
                        f"{output_source_id}_{unit_id}_{index:03d}"
                    ),
                    "text": chunk,
                    "source_id": output_source_id,
                    "parent_source_id": source["source_id"],
                    "title": source["title"],
                    "source_org": source["source_org"],
                    "source_url": source["source_url"],
                    "jurisdiction": source["jurisdiction"],
                    "target_population": source["target_population"],
                    "version": f"{source['version']}+curated-v0.1",
                    "effective_date": source["effective_date"],
                    "expiry_date": source.get("expiry_date", ""),
                    "authority_level": source["authority_level"],
                    "hazard_types": unit_hazard_types,
                    "applicability": source["applicability"],
                    "status": "draft",
                    "source_tier": source["source_tier"],
                    "content_review_status": "pending_double_review",
                    "license_status": source["license_status"],
                    "redistribution_status": source["redistribution_status"],
                    "file_sha256": derived_sha256,
                    "parent_file_sha256": source["file_sha256"],
                    "source_locator": locator,
                    "derivation_method": "deterministic_rule_v0.1",
                    "derivation_rule_reason": rule.get("reason", ""),
                }
            )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按预注册页码和章节规则生成协议派生候选及精选切块。"
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--derived-directory", required=True)
    parser.add_argument("--derived-registry", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--target-characters", type=int, default=600)
    parser.add_argument("--overlap-characters", type=int, default=80)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry).resolve()
    rules_path = Path(args.rules).resolve()
    derived_directory = Path(args.derived_directory).resolve()
    derived_registry_path = Path(args.derived_registry).resolve()
    chunks_path = Path(args.chunks).resolve()
    report_path = Path(args.report).resolve()

    sources = {
        str(row["source_id"]): row for row in read_jsonl(registry_path)
    }
    rules = read_jsonl(rules_path)
    chunks: list[dict[str, Any]] = []
    derived_registry: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []

    for rule in rules:
        parent_source_id = str(rule["parent_source_id"])
        if parent_source_id not in sources:
            raise ValueError(f"rule references unknown source {parent_source_id}")
        source = sources[parent_source_id]
        if rule["mode"] == "exclude_direct_retrieval":
            excluded.append(
                {
                    "parent_source_id": parent_source_id,
                    "reason": str(rule["reason"]),
                }
            )
            continue

        source_path = (
            registry_path.parent / str(source["file"])
        ).resolve()
        if sha256_file(source_path) != source["file_sha256"]:
            raise ValueError(f"{parent_source_id}: parent file hash mismatch")

        if rule["mode"] == "pdf_pages":
            units = extract_pdf_units(
                source_path,
                [int(page) for page in rule["include_pages"]],
                {
                    str(unit_id): dict(trim)
                    for unit_id, trim in rule.get("unit_trims", {}).items()
                },
            )
        elif rule["mode"] == "text_sections":
            units = extract_text_units(source_path, list(rule["sections"]))
        else:
            raise ValueError(f"unsupported mode: {rule['mode']}")

        forbidden_terms = [str(item) for item in rule.get("forbidden_terms", [])]
        forbidden_hits = {
            term: [unit_id for unit_id, _, text in units if term in text]
            for term in forbidden_terms
        }
        forbidden_hits = {
            term: unit_ids for term, unit_ids in forbidden_hits.items() if unit_ids
        }
        if forbidden_hits:
            raise ValueError(
                f"{parent_source_id}: forbidden terms found: {forbidden_hits}"
            )

        derived_path = derived_directory / str(rule["output_file"])
        write_derived_markdown(
            derived_path,
            source=source,
            rule=rule,
            units=units,
        )
        derived_sha256 = sha256_file(derived_path)
        source_chunks = build_chunks(
            source,
            rule,
            units,
            derived_sha256=derived_sha256,
            target_characters=args.target_characters,
            overlap_characters=args.overlap_characters,
        )
        chunks.extend(source_chunks)

        manual_terms = [
            str(item) for item in rule.get("manual_review_terms", [])
        ]
        manual_hits = {
            term: [unit_id for unit_id, _, text in units if term in text]
            for term in manual_terms
        }
        manual_hits = {
            term: unit_ids for term, unit_ids in manual_hits.items() if unit_ids
        }
        derived_registry.append(
            {
                "source_id": rule["output_source_id"],
                "parent_source_id": parent_source_id,
                "title": source["title"],
                "file": str(derived_path.relative_to(derived_registry_path.parent)).replace("\\", "/"),
                "file_sha256": derived_sha256,
                "parent_file_sha256": source["file_sha256"],
                "source_org": source["source_org"],
                "source_url": source["source_url"],
                "jurisdiction": source["jurisdiction"],
                "target_population": source["target_population"],
                "version": f"{source['version']}+curated-v0.1",
                "effective_date": source["effective_date"],
                "authority_level": source["authority_level"],
                "hazard_types": source["hazard_types"],
                "applicability": source["applicability"],
                "status": "draft",
                "content_review_status": "pending_double_review",
                "license_status": source["license_status"],
                "redistribution_status": source["redistribution_status"],
                "derivation_method": "deterministic_rule_v0.1",
            }
        )
        results.append(
            {
                "source_id": rule["output_source_id"],
                "parent_source_id": parent_source_id,
                "units": len(units),
                "chunks": len(source_chunks),
                "derived_file": str(derived_path),
                "derived_sha256": derived_sha256,
                "manual_review_hits": manual_hits,
                "replacement_characters": sum(
                    text.count("�") for _, _, text in units
                ),
            }
        )

    evidence_ids = [str(row["evidence_id"]) for row in chunks]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("duplicate derived evidence_id")
    write_jsonl(derived_registry_path, derived_registry)
    write_jsonl(chunks_path, chunks)
    report = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "formal_knowledge_base_eligible": False,
        "reason": "machine curated output pending double content and license review",
        "inputs": {
            "registry": str(registry_path),
            "registry_sha256": sha256_file(registry_path),
            "rules": str(rules_path),
            "rules_sha256": sha256_file(rules_path),
        },
        "outputs": {
            "derived_registry": str(derived_registry_path),
            "derived_registry_sha256": sha256_file(derived_registry_path),
            "chunks": str(chunks_path),
            "chunks_sha256": sha256_file(chunks_path),
        },
        "sources_included": len(results),
        "sources_excluded_from_direct_retrieval": excluded,
        "chunks": len(chunks),
        "results": results,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "sources_included": len(results),
                "sources_excluded": len(excluded),
                "chunks": len(chunks),
                "formal_knowledge_base_eligible": False,
                "report": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
