import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from sci_exp.schemas import ProtocolChunk


CHUNKS_PATH = (
    PROJECT_ROOT / "data" / "processed" / "精选候选协议切块_v0.1.jsonl"
)
DERIVED_REGISTRY_PATH = (
    PROJECT_ROOT / "data" / "processed" / "协议派生登记_v0.1.jsonl"
)
PILOT_PATH = (
    PROJECT_ROOT
    / "data"
    / "annotations"
    / "先导24条证据绑定候选_v0.1.jsonl"
)
PILOT_REPORT_PATH = (
    PROJECT_ROOT / "data" / "logs" / "先导证据建议报告_v0.1.json"
)
ADJUDICATED_PATH = (
    PROJECT_ROOT
    / "data"
    / "annotations"
    / "先导24条证据仲裁结果_v0.1.jsonl"
)
DOUBLE_REVIEW_REPORT_PATH = (
    PROJECT_ROOT / "data" / "logs" / "先导24条双审一致性报告_v0.1.json"
)


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class ProtocolDerivationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.chunks = read_jsonl(CHUNKS_PATH)
        cls.chunk_ids = {row["evidence_id"] for row in cls.chunks}
        cls.pilot = read_jsonl(PILOT_PATH)

    def test_curated_chunks_are_traceable_but_not_formal(self) -> None:
        self.assertEqual(64, len(self.chunks))
        self.assertEqual(64, len(self.chunk_ids))
        self.assertEqual(
            {
                "NHC_HEALTH_LITERACY_2024",
                "MEM_EARTHQUAKE_SAFETY_2025",
                "MEM_FLOOD_SAFETY_2025",
                "MEM_HIGHRISE_FIRE_ORDER5",
                "CMA_WARNING_SIGNALS_ORDER16",
                "SHQP_HEAD_TRAUMA_2018",
                "BJWJW_HYPOTHERMIA_2022",
                "BJWJW_CRUSH_INJURY_2019",
                "MEM_EARTHQUAKE_FIRST_AID_2019",
                "JINCHENG_HIGHRISE_FIRE_2026",
                "NHC_PSYCHOLOGICAL_HOTLINE_2021",
                "NHC_DISASTER_ENV_HEALTH_2019",
                "MEM_FLOOD_PREPAREDNESS_2026",
            },
            {row["parent_source_id"] for row in self.chunks},
        )
        for row in self.chunks:
            self.assertEqual("draft", row["status"])
            self.assertEqual(
                "pending_double_review", row["content_review_status"]
            )
            self.assertEqual(
                "pending_manual_confirmation", row["license_status"]
            )
            self.assertTrue(row["parent_file_sha256"])
            self.assertTrue(row["file_sha256"])
            self.assertTrue(row["source_locator"])
            self.assertNotIn("�", row["text"])
            self.assertNotIn("尿液", row["text"])

    def test_page_specific_hazard_tags_do_not_leak_across_pages(self) -> None:
        p049 = [
            row
            for row in self.chunks
            if "_p049_" in row["evidence_id"]
        ]
        p052 = [
            row
            for row in self.chunks
            if "_p052_" in row["evidence_id"]
        ]
        self.assertTrue(p049)
        self.assertTrue(p052)
        self.assertTrue(
            all(row["hazard_types"] == ["emergency_call"] for row in p049)
        )
        self.assertTrue(
            all("fracture" in row["hazard_types"] for row in p052)
        )
        self.assertTrue(
            all("体重测量方法" not in row["text"] for row in p049)
        )

    def test_derived_registry_paths_are_radxa_portable(self) -> None:
        registry = read_jsonl(DERIVED_REGISTRY_PATH)
        self.assertEqual(13, len(registry))
        for row in registry:
            file_value = row["file"]
            self.assertFalse(Path(file_value).is_absolute())
            self.assertNotIn("D:\\", file_value)
            self.assertTrue(
                (DERIVED_REGISTRY_PATH.parent / file_value).is_file()
            )

    def test_protocol_chunk_roundtrip_preserves_lineage(self) -> None:
        original = self.chunks[0]
        restored = ProtocolChunk.from_dict(original).to_dict()
        for field in (
            "parent_source_id",
            "parent_file_sha256",
            "source_locator",
            "derivation_method",
            "derivation_rule_reason",
        ):
            self.assertEqual(original[field], restored[field])

    def test_pilot_suggestions_never_populate_gold_labels(self) -> None:
        self.assertEqual(24, len(self.pilot))
        self.assertEqual(
            24, len({row["source_group_id"] for row in self.pilot})
        )
        for row in self.pilot:
            self.assertFalse(row["formal_training_eligible"])
            self.assertEqual([], row["gold_evidence_ids"])
            self.assertEqual("", row["split"])
            self.assertEqual(
                "machine_suggestion_pending_double_review",
                row["evidence_binding_status"],
            )
            for candidate in row["machine_candidate_evidence"]:
                self.assertIn(candidate["evidence_id"], self.chunk_ids)

    def test_only_designed_evidence_gaps_remain(self) -> None:
        report = json.loads(PILOT_REPORT_PATH.read_text(encoding="utf-8"))
        expected_gap_intents = {"out_of_scope"}
        actual_gap_intents = {
            row["legacy_primary_intent"]
            for row in self.pilot
            if row["evidence_gap_flag"]
        }
        self.assertEqual(expected_gap_intents, actual_gap_intents)
        self.assertEqual([], report["unexpected_evidence_gap_rows"])

    def test_adjudicated_rows_are_complete_but_not_formal(self) -> None:
        rows = read_jsonl(ADJUDICATED_PATH)
        self.assertEqual(24, len(rows))
        self.assertEqual(24, len({row["query_id"] for row in rows}))
        for row in rows:
            self.assertEqual("adjudicated", row["annotation_status"])
            self.assertFalse(row["formal_training_eligible"])
            self.assertEqual("", row["split"])
            self.assertTrue(row["required_actions"])
            self.assertTrue(row["prohibited_actions"])
            self.assertFalse(
                set(row["required_actions"])
                & set(row["prohibited_actions"])
            )
            self.assertTrue(
                set(row["gold_evidence_ids"]).issubset(self.chunk_ids)
            )

    def test_double_review_agreement_meets_pilot_threshold(self) -> None:
        report = json.loads(
            DOUBLE_REVIEW_REPORT_PATH.read_text(encoding="utf-8")
        )
        agreement = report["agreement"]
        self.assertGreaterEqual(
            agreement["risk_level_cohen_kappa"], 0.70
        )
        self.assertGreaterEqual(
            agreement["fallback_cohen_kappa"], 0.70
        )
        self.assertGreaterEqual(
            agreement["evidence_mean_jaccard"], 0.70
        )
        self.assertEqual(
            {"L0": 2, "L1": 5, "L2": 8, "L3": 9},
            report["adjudicated_distribution"]["risk_level"],
        )

    def test_adjudication_rejects_known_cross_context_matches(self) -> None:
        rows = {
            row["query_id"]: row for row in read_jsonl(ADJUDICATED_PATH)
        }
        respiratory_ids = {
            evidence_id
            for query_id in (
                "pilot_legacy_clean_0005",
                "pilot_legacy_multi_0107",
                "pilot_legacy_multi_0031",
            )
            for evidence_id in rows[query_id]["gold_evidence_ids"]
        }
        self.assertNotIn(
            "NHC_HEALTH_LITERACY_2024_CURATED_V01_p053_001",
            respiratory_ids,
        )
        self.assertNotIn(
            "NHC_HEALTH_LITERACY_2024_CURATED_V01_p055_001",
            rows["pilot_legacy_clean_0078"]["gold_evidence_ids"],
        )
        trapped_thirsty = rows["pilot_legacy_clean_0137"]
        self.assertTrue(trapped_thirsty["should_fallback"])
        self.assertEqual(
            {
                "NHC_HEALTH_LITERACY_2024_CURATED_V01_p055_001",
                "NHC_DISASTER_ENV_HEALTH_2019_CURATED_V01_p007_001",
            },
            set(trapped_thirsty["gold_evidence_ids"]),
        )
        self.assertFalse(
            any(
                evidence_id.startswith("JINCHENG_HIGHRISE_FIRE")
                or evidence_id.startswith("MEM_FLOOD_SAFETY")
                for evidence_id in trapped_thirsty["gold_evidence_ids"]
            )
        )

    def test_selected_sections_exclude_known_unsafe_context(self) -> None:
        text_by_parent: dict[str, str] = {}
        for row in self.chunks:
            text_by_parent.setdefault(row["parent_source_id"], "")
            text_by_parent[row["parent_source_id"]] += "\n" + row["text"]

        self.assertNotIn(
            "头向后仰",
            text_by_parent["SHQP_HEAD_TRAUMA_2018"],
        )
        self.assertNotIn(
            "糖盐水",
            text_by_parent["MEM_EARTHQUAKE_FIRST_AID_2019"],
        )
        self.assertNotIn(
            "自杀计划",
            text_by_parent["NHC_PSYCHOLOGICAL_HOTLINE_2021"],
        )
        self.assertNotIn(
            "漂白粉",
            text_by_parent["NHC_DISASTER_ENV_HEALTH_2019"],
        )


if __name__ == "__main__":
    unittest.main()
