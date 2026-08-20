from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sci_exp.schemas import QueryRecord  # noqa: E402
from sci_exp.splitting import DEFAULT_PROPORTIONS, group_split  # noqa: E402
from sci_exp.validation import validate_no_group_leakage, validate_queries  # noqa: E402


SPLITS = ("train", "valid", "cal_op", "cal_ch", "test_op", "test_ch")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按source_group_id冻结400条查询的六分区。")
    parser.add_argument("--input", required=True)
    parser.add_argument("--protocols", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--combined-output", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def split_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n": len(rows),
        "source_groups": len({row["source_group_id"] for row in rows}),
        "l3": sum(row["risk_level"] == 3 for row in rows),
        "c3_fallback": sum(bool(row["should_fallback"]) for row in rows),
        "out_of_scope": sum(bool(row.get("expected_gap_control")) for row in rows),
        "risk_distribution": dict(
            sorted(Counter(f"L{row['risk_level']}" for row in rows).items())
        ),
    }


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    protocol_path = Path(args.protocols).resolve()
    output_directory = Path(args.output_directory).resolve()
    combined_path = Path(args.combined_output).resolve()
    manifest_path = Path(args.manifest).resolve()

    raw_rows = read_jsonl(input_path)
    protocols = read_jsonl(protocol_path)
    protocol_ids = {str(row["evidence_id"]) for row in protocols}
    queries = [QueryRecord.from_dict(row) for row in raw_rows]
    if len(queries) != 400:
        raise ValueError("六分区输入必须恰好为400条")
    errors = validate_queries(queries, protocol_ids)
    if errors:
        raise ValueError(f"查询校验失败：{errors[:10]}")

    frozen = group_split(queries, seed=args.seed)
    leakage = validate_no_group_leakage(frozen)
    if leakage:
        raise ValueError(f"分组泄漏：{leakage}")
    by_split: dict[str, list[dict[str, Any]]] = {name: [] for name in SPLITS}
    for query in frozen:
        by_split[query.split].append(query.to_dict())
    if any(not by_split[name] for name in SPLITS):
        raise ValueError("六分区中存在空分区")

    output_directory.mkdir(parents=True, exist_ok=True)
    split_hashes: dict[str, str] = {}
    for name in SPLITS:
        path = output_directory / f"{name}.jsonl"
        rows = sorted(by_split[name], key=lambda row: str(row["query_id"]))
        write_jsonl(path, rows)
        split_hashes[name] = sha256(path)

    combined_rows = [
        row
        for name in SPLITS
        for row in sorted(by_split[name], key=lambda value: str(value["query_id"]))
    ]
    write_jsonl(combined_path, combined_rows)
    summaries = {name: split_summary(by_split[name]) for name in SPLITS}
    global_groups = {
        name: {row["source_group_id"] for row in by_split[name]} for name in SPLITS
    }
    pairwise_disjoint = all(
        not (global_groups[left] & global_groups[right])
        for index, left in enumerate(SPLITS)
        for right in SPLITS[index + 1 :]
    )
    challenge_coverage = all(
        summaries[name]["l3"] > 0
        and summaries[name]["c3_fallback"] > 0
        and summaries[name]["out_of_scope"] > 0
        for name in ("cal_ch", "test_ch")
    )
    gates = {
        "exactly_400_rows": len(combined_rows) == 400,
        "all_six_splits_nonempty": all(bool(by_split[name]) for name in SPLITS),
        "source_groups_pairwise_disjoint": pairwise_disjoint,
        "challenge_calibration_and_test_cover_l3_c3_out_of_scope": challenge_coverage,
        "all_evidence_ids_exist": all(
            set(row.get("gold_evidence_ids", [])) <= protocol_ids
            for row in combined_rows
        ),
        "all_adjudicated": all(
            row.get("annotation_status") in {"adjudicated", "quality_checked", "frozen"}
            for row in combined_rows
        ),
    }
    if not all(gates.values()):
        raise ValueError(f"六分区冻结门槛未通过：{gates}")

    manifest = {
        "manifest_version": "v1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "method": "sha256_source_group_assignment",
        "proportions": DEFAULT_PROPORTIONS,
        "input": {
            "path": str(input_path),
            "sha256": sha256(input_path),
            "protocols_sha256": sha256(protocol_path),
        },
        "split_summary": summaries,
        "split_sha256": split_hashes,
        "combined_output_sha256": sha256(combined_path),
        "quality_gates": gates,
        "interpretation": (
            "按source_group_id整体分配；实际行数允许偏离名义比例，"
            "以避免同源场景跨分区泄漏。"
        ),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"split_summary": summaries, "quality_gates": gates}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
