import json
import csv
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = PROJECT_ROOT / "docs" / "研究协议_v1.md"
CONFIRMATORY_PROTOCOL = (
    PROJECT_ROOT / "docs" / "研究协议_v2.0_确认性设计冻结.md"
)
CURRENT_PROTOCOL = PROJECT_ROOT / "docs" / "研究协议_v3.0_SC-EA-RAG重构.md"
ENDPOINT_TABLE = PROJECT_ROOT / "docs" / "主要终点与假设表_v2.0.csv"
DEVICE_LOCK = PROJECT_ROOT / "docs" / "设备与软件环境锁定表_v1.0.yaml"
VERSION_RULES = PROJECT_ROOT / "docs" / "研究资产版本命名规则_v1.0.md"
PILOT_CANDIDATES = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "queries"
    / "旧项目先导候选查询_v0.1.jsonl"
)
ANNOTATION_TEMPLATE = (
    PROJECT_ROOT
    / "data"
    / "annotations"
    / "先导查询重新标注模板_v0.1.csv"
)
IMPORT_REPORT = (
    PROJECT_ROOT
    / "data"
    / "logs"
    / "旧项目先导数据导入报告_v0.1.json"
)


class ResearchContractTests(unittest.TestCase):
    def test_pilot_contract_assets_exist(self) -> None:
        for path in (
            PROTOCOL,
            PILOT_CANDIDATES,
            ANNOTATION_TEMPLATE,
            IMPORT_REPORT,
        ):
            self.assertTrue(path.is_file(), str(path))

    def test_protocol_marks_legacy_pool_as_non_formal(self) -> None:
        text = PROTOCOL.read_text(encoding="utf-8")
        self.assertIn("不属于当前正式训练数据", text)
        self.assertIn("必须与当前协议重新对齐", text)
        self.assertIn("只有A/B级来源可以支撑正式协议答案", text)

    def test_legacy_pool_is_traceable_and_not_training_eligible(self) -> None:
        rows = [
            json.loads(line)
            for line in PILOT_CANDIDATES.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        ]
        self.assertEqual(len(rows), 120)
        self.assertEqual(len({row["query_id"] for row in rows}), 120)
        self.assertTrue(all(row["split"] == "" for row in rows))
        self.assertTrue(
            all(row["formal_training_eligible"] is False for row in rows)
        )
        self.assertTrue(
            all(
                row["pilot_status"]
                == "needs_protocol_grounding_and_current_reannotation"
                for row in rows
            )
        )
        self.assertTrue(all(row["legacy_source"] for row in rows))
        self.assertTrue(all(row["source_group_id"] for row in rows))
        self.assertTrue(all(not row["gold_evidence_ids"] for row in rows))

    def test_import_report_records_source_and_limitations(self) -> None:
        report = json.loads(IMPORT_REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["counts"]["rows"], 120)
        self.assertEqual(report["counts"]["formal_training_eligible"], 0)
        self.assertEqual(
            sum(report["distribution"]["query_type"].values()),
            120,
        )
        self.assertTrue(report["input"]["sha256"])
        self.assertGreaterEqual(len(report["limitations"]), 5)

    def test_confirmatory_design_is_frozen_and_current_400_is_development(self) -> None:
        for path in (
            CONFIRMATORY_PROTOCOL,
            ENDPOINT_TABLE,
            DEVICE_LOCK,
            VERSION_RULES,
        ):
            self.assertTrue(path.is_file(), str(path))
        text = CONFIRMATORY_PROTOCOL.read_text(encoding="utf-8")
        self.assertIn("核心基础查询数为3,600条", text)
        self.assertIn("| `test_op` | 1,200 |", text)
        self.assertIn("不得进入最终`cal_op`", text)
        self.assertIn("- 真实参与者实验；", text)
        self.assertIn("第二台设备", text)

    def test_current_sc_ea_rag_protocol_supersedes_v2_for_execution(self) -> None:
        text = CURRENT_PROTOCOL.read_text(encoding="utf-8")
        self.assertIn("替代v2.0作为后续", text)
        self.assertIn("y_trigger", text)
        self.assertIn("y_miss", text)
        self.assertIn("y_quality", text)
        self.assertIn("不低于100Hz", text)
        self.assertIn("不得直接沿用v2.0的3600条设计", text)

    def test_exactly_one_confirmatory_primary_hypothesis(self) -> None:
        with ENDPOINT_TABLE.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        primary = [row for row in rows if row["层级"] == "确认性主要"]
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0]["编号"], "H_PRIMARY")
        self.assertIn("固定C2", primary[0]["比较"])

    def test_device_lock_blocks_execution_until_radxa_probe(self) -> None:
        text = DEVICE_LOCK.read_text(encoding="utf-8")
        self.assertIn('status: "blocked_pending_radxa_probe"', text)
        self.assertIn("second_device_in_confirmatory_study: false", text)
        self.assertIn("confirmatory_execution_allowed: false", text)


if __name__ == "__main__":
    unittest.main()
