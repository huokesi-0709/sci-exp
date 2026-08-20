from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPLIT_ROOT = ROOT / "data" / "splits_stratified_v2"
SPLITS = ("train", "valid", "cal_op", "cal_ch", "test_op", "test_ch")


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(character for character in text if character.isalnum())


def all_rows() -> list[dict]:
    return [row for split in SPLITS for row in read_jsonl(SPLIT_ROOT / f"{split}.jsonl")]


def test_v2_manifest_hashes_and_gates() -> None:
    manifest_path = SPLIT_ROOT / "正式400条分层六分区清单_v2.0.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["method"] == "explicit_scenario_stratification_without_hash_assignment"
    assert manifest["policy"]["hash_used_for_assignment"] is False
    assert all(manifest["quality_gates"].values())
    for split in SPLITS:
        assert manifest["split_sha256"][split] == sha256(
            SPLIT_ROOT / f"{split}.jsonl"
        )


def test_v2_has_400_unique_queries_and_required_quotas() -> None:
    rows = all_rows()
    assert len(rows) == 400
    assert len({row["query_id"] for row in rows}) == 400
    assert len({normalized(row["text"]) for row in rows}) == 400
    assert len({row["source_group_id"] for row in rows}) >= 40
    assert sum(row["risk_level"] == 3 for row in rows) >= 100
    assert sum(bool(row["should_fallback"]) for row in rows) >= 100
    assert sum(bool(row["expected_gap_control"]) for row in rows) >= 30


def test_v2_source_and_near_duplicate_units_do_not_leak() -> None:
    rows = all_rows()
    source_splits: dict[str, set[str]] = {}
    unit_splits: dict[str, set[str]] = {}
    for row in rows:
        source_splits.setdefault(row["source_group_id"], set()).add(row["split"])
        unit_splits.setdefault(row["partition_unit_id"], set()).add(row["split"])
    assert all(len(splits) == 1 for splits in source_splits.values())
    assert all(len(splits) == 1 for splits in unit_splits.values())


def test_operational_and_challenge_roles_are_explicit() -> None:
    for split in ("train", "valid", "cal_op", "test_op"):
        rows = read_jsonl(SPLIT_ROOT / f"{split}.jsonl")
        assert any(row["risk_level"] == 3 for row in rows)
        assert any(row["should_fallback"] for row in rows)
    for split in ("cal_op", "test_op"):
        rows = read_jsonl(SPLIT_ROOT / f"{split}.jsonl")
        assert all(not row["temporal_ood"] for row in rows)
        assert all(not row["regional_ood"] for row in rows)
        assert all(not row["expected_gap_control"] for row in rows)


def test_time_and_region_holdouts_only_appear_in_test_ch() -> None:
    rows = all_rows()
    temporal = [row for row in rows if row["temporal_ood"]]
    regional = [row for row in rows if row["regional_ood"]]
    assert len(temporal) == 37
    assert len(regional) == 28
    assert {row["split"] for row in temporal} == {"test_ch"}
    assert {row["split"] for row in regional} == {"test_ch"}


def test_version_ood_is_documented_as_unavailable() -> None:
    manifest = json.loads(
        (SPLIT_ROOT / "正式400条分层六分区清单_v2.0.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["holdouts"]["version"]["constructible"] is False
    assert all(not row["version_ood"] for row in all_rows())
