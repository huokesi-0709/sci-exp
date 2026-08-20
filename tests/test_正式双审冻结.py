from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "执行96条正式双审与样本量复核.py"


def load_review_module():
    spec = importlib.util.spec_from_file_location("formal_review", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def query(text: str, disaster_type: str = "earthquake") -> dict[str, str]:
    return {
        "text": text,
        "query_type": "single_intent",
        "disaster_type": disaster_type,
    }


def test_negated_bleeding_does_not_escalate_head_dizziness_to_l3():
    module = load_review_module()
    tags = module.tags_for(query("我头晕，不过没有头部出血"))
    assert tags["head"] is True
    assert tags["severe_bleeding"] is False
    assert module.risk_from_tags(tags) == 2


def test_negated_respiratory_phrase_is_not_respiratory_distress():
    module = load_review_module()
    tags = module.tags_for(query("我不是喘不上气，只是有点慌"))
    assert tags["respiratory"] is False
    assert module.risk_from_tags(tags) != 3


def test_formal_source_groups_match_final_evidence_bindings():
    rows_path = ROOT / "data" / "annotations" / "正式96条仲裁结果_v1.0.jsonl"
    rows = [
        json.loads(line)
        for line in rows_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 96
    assert len({row["source_group_id"] for row in rows}) == 21
    for row in rows:
        event, family, version = row["source_group_id"].split("|", maxsplit=2)
        assert event == row["event_cluster"]
        assert family == row["protocol_family"]
        assert version == row["protocol_version_chain"]


def test_who_license_records_are_not_conflated():
    table = ROOT / "data" / "annotations" / "许可与版本核验表_v1.0.csv"
    with table.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = {row["source_id"]: row for row in csv.DictReader(handle)}

    bec = rows["WHO_ICRC_BEC_2018"]
    pfa = rows["WHO_PFA_2011"]
    assert bec["正文中观察到的许可声明"] == "CC BY-NC-SA 3.0 IGO"
    assert bec["公开再分发资格"] == "true"
    assert "All rights reserved" in pfa["正文中观察到的许可声明"]
    assert pfa["公开再分发资格"] == "false"
