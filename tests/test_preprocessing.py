import unittest

from sci_exp.preprocessing import (
    normalize_text,
    preprocess_query_rows,
    preprocess_resource_rows,
)


def query_row(query_id: str, text: str, group: str) -> dict:
    return {
        "query_id": query_id,
        "text": text,
        "disaster_type": "fire",
        "query_type": "single_action",
        "risk_level": 3,
        "language": "zh",
        "should_fallback": False,
        "gold_evidence_ids": ["fire_001"],
        "required_actions": ["撤离"],
        "prohibited_actions": ["使用电梯"],
        "source_group_id": group,
    }


class PreprocessingTests(unittest.TestCase):
    def test_normalize_text_is_deterministic(self) -> None:
        value = "ＡＢＣ\u200b  \r\n\r\n\r\n 测试 "
        self.assertEqual(normalize_text(value), "ABC\n\n测试")

    def test_sensitive_query_is_quarantined_and_redacted(self) -> None:
        result = preprocess_query_rows(
            [query_row("q1", "请联系我 13812345678 处理火灾", "g1")]
        )
        self.assertEqual(result.records, [])
        self.assertEqual(len(result.quarantine), 1)
        self.assertIn(
            "sensitive_text:phone",
            result.quarantine[0]["reasons"],
        )
        self.assertNotIn(
            "13812345678",
            result.quarantine[0]["record"]["text"],
        )

    def test_meaningful_short_emergency_query_is_retained_as_challenge(self) -> None:
        result = preprocess_query_rows(
            [
                {
                    **query_row("q_short", "我没水", "g_short"),
                    "risk_level": 1,
                    "should_fallback": True,
                }
            ]
        )
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.quarantine, [])
        self.assertTrue(
            result.records[0]["preprocessing"]["short_query_challenge"]
        )
        self.assertIn("short_query_challenge", [
            event["code"] for event in result.events
        ])

    def test_meaningless_short_query_is_still_quarantined(self) -> None:
        result = preprocess_query_rows(
            [
                {
                    **query_row("q_too_short", "好", "g_short"),
                    "risk_level": 0,
                    "should_fallback": False,
                }
            ]
        )
        self.assertEqual(result.records, [])
        self.assertIn("text_too_short", result.quarantine[0]["reasons"])

    def test_group_split_happens_before_train_only_augmentation(self) -> None:
        rows = [
            query_row(f"q{index}", f"第{index}个火灾问题怎么办", f"g{index}")
            for index in range(30)
        ]
        result = preprocess_query_rows(
            rows,
            seed=42,
            augment_train_copies=1,
        )
        augmented = [
            row for row in result.records if "augmentation_parent_id" in row
        ]
        self.assertTrue(augmented)
        self.assertTrue(all(row["split"] == "train" for row in augmented))
        parent_split = {
            row["query_id"]: row["split"]
            for row in result.records
            if "augmentation_parent_id" not in row
        }
        self.assertTrue(
            all(
                parent_split[row["augmentation_parent_id"]] == "train"
                for row in augmented
            )
        )

    def test_conflicting_duplicate_ids_are_all_quarantined(self) -> None:
        result = preprocess_query_rows(
            [
                query_row("q1", "发现火灾应该怎么办", "g1"),
                query_row("q1", "发现浓烟应该怎么办", "g1"),
            ]
        )
        self.assertEqual(result.records, [])
        self.assertEqual(len(result.quarantine), 2)
        self.assertTrue(
            all(
                "duplicate_conflicting_query_id" in item["reasons"]
                for item in result.quarantine
            )
        )

    def test_resource_outlier_is_flagged_not_deleted(self) -> None:
        rows = []
        for index, latency in enumerate([100, 101, 99, 102, 100, 10000]):
            rows.append(
                {
                    "status": "ok",
                    "query_id": f"q{index}",
                    "configuration": "C1",
                    "repetition": index,
                    "latency_ms": latency,
                    "telemetry": {
                        "energy_j": 1.0,
                        "process_peak_rss_mb": 100.0,
                    },
                }
            )
        result = preprocess_resource_rows(rows)
        self.assertEqual(len(result.records), 6)
        flags = [
            flag
            for row in result.records
            for flag in row["preprocessing"]["outlier_flags"]
        ]
        self.assertIn("latency_ms:robust_z", flags)

    def test_missing_energy_can_only_be_allowed_explicitly(self) -> None:
        row = {
            "status": "ok",
            "query_id": "q1",
            "configuration": "C1",
            "repetition": 0,
            "latency_ms": 10,
            "telemetry": {
                "energy_j": None,
                "process_peak_rss_mb": 100,
            },
        }
        strict = preprocess_resource_rows([row], require_energy=True)
        permissive = preprocess_resource_rows([row], require_energy=False)
        self.assertEqual(len(strict.quarantine), 1)
        self.assertEqual(len(permissive.records), 1)


if __name__ == "__main__":
    unittest.main()
