from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPLITS = ("train", "valid", "cal_op", "cal_ch", "test_op", "test_ch")


def read_jsonl(path: Path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_formal_400_quotas_are_met():
    report = json.loads(
        (ROOT / "data" / "logs" / "正式400条双审与配额报告_v1.0.json").read_text(
            encoding="utf-8"
        )
    )
    assert all(report["gates"].values())
    assert report["counts"]["total"] == 400
    assert report["counts"]["source_groups"] >= 40
    assert report["counts"]["l3"] >= 100
    assert report["counts"]["c3_fallback"] >= 100
    assert report["counts"]["out_of_scope"] >= 30


def test_frozen_splits_are_hash_locked_and_group_disjoint():
    manifest_path = ROOT / "data" / "splits" / "正式400条六分区清单_v1.0.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert all(manifest["quality_gates"].values())
    seen_groups: set[str] = set()
    total = 0
    for name in SPLITS:
        path = ROOT / "data" / "splits" / f"{name}.jsonl"
        rows = read_jsonl(path)
        groups = {row["source_group_id"] for row in rows}
        assert not (seen_groups & groups)
        seen_groups |= groups
        total += len(rows)
        assert sha256(path) == manifest["split_sha256"][name]
    assert total == 400


def test_windows_preprocess_preserved_all_frozen_rows():
    report = json.loads(
        (
            ROOT
            / "data"
            / "formal_preprocess_v1.0"
            / "logs"
            / "query_preprocess_report.json"
        ).read_text(encoding="utf-8")
    )
    assert report["counts"]["accepted_base_rows"] == 400
    assert report["counts"]["quarantined_rows"] == 0
    assert report["parameters"]["preserve_existing_splits"] is True
    assert report["quality_gates"]["frozen_splits_preserved"] is True


def test_formal_protocol_library_is_internal_research_scoped():
    rows = read_jsonl(ROOT / "data" / "processed" / "protocols.jsonl")
    assert len(rows) == 64
    assert len({row["evidence_id"] for row in rows}) == 64
    assert all(
        row["formal_library_scope"]
        == "local_noncommercial_scientific_research_no_republication"
        for row in rows
    )
