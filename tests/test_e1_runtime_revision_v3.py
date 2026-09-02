import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class E1RuntimeRevisionV3Tests(unittest.TestCase):
    def test_v3_changes_only_timeout_and_declared_output_from_v2(self) -> None:
        v2 = json.loads((ROOT / "configs" / "E1_devtemp_v2.json").read_text(encoding="utf-8"))
        v3 = json.loads((ROOT / "configs" / "E1_devtemp_v3.json").read_text(encoding="utf-8"))
        self.assertEqual(v3["generator"]["timeout_seconds"], 420)
        self.assertEqual(v2["generator"]["timeout_seconds"], 300)
        v2["generator"]["timeout_seconds"] = v3["generator"]["timeout_seconds"]
        v2["experiment"]["output"] = v3["experiment"]["output"]
        self.assertEqual(v2, v3)

    def test_v3_preflight_is_single_nonformal_long_c2_task(self) -> None:
        revision = json.loads(
            (ROOT / "configs" / "E1_runtime_revision_v3_20260901.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(revision["formal_evidence"])
        self.assertEqual(revision["preflight_gate"]["run_order"], 21)
        self.assertEqual(revision["preflight_gate"]["run_key"], "formal_exp_0171:C2:2")
        self.assertEqual(revision["candidate_runtime"]["timeout_seconds"], 420)

    def test_formal_v3_runtime_lock_references_the_qualified_candidate(self) -> None:
        lock = json.loads(
            (ROOT / "configs" / "E1_formal_runtime_lock_v3_20260901.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(lock["status"], "locked_ready_for_new_formal_B01_003")
        self.assertEqual(lock["runtime_revision"]["request_timeout_seconds"], 420)
        self.assertEqual(lock["new_formal_batch"]["run_order_start"], 1)
        self.assertEqual(lock["new_formal_batch"]["run_order_end"], 63)
        self.assertFalse(lock["new_formal_batch"]["overwrite_allowed"])

    def test_b01_result_is_complete_and_has_valid_external_meter_rows(self) -> None:
        result = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B01_003_result_v1.0.json").read_text(
                encoding="utf-8"
            )
        )
        runs = [
            json.loads(line)
            for line in (ROOT / result["energy_integration"]["merged_output"])
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        self.assertTrue(result["formal_evidence"])
        self.assertEqual(result["runner"]["successful"], 63)
        self.assertEqual(result["energy_integration"]["valid_count"], 63)
        self.assertEqual(len(runs), 63)
        self.assertTrue(all(row["status"] == "ok" for row in runs))
        self.assertTrue(
            all((row.get("telemetry") or {}).get("external_meter_valid") for row in runs)
        )

    def test_b02_lock_is_contiguous_and_does_not_overlap_b01(self) -> None:
        lock = json.loads(
            (ROOT / "configs" / "E1_formal_batch_B02_lock_v3_20260902.json").read_text(
                encoding="utf-8"
            )
        )
        design = lock["design"]
        self.assertEqual(design["previous_batch_range"], [1, 63])
        self.assertEqual(design["global_run_order_start"], 64)
        self.assertEqual(design["global_run_order_end"], 126)
        self.assertEqual(design["expected_run_count"], 63)
        self.assertFalse(lock["artifacts"]["overwrite_allowed"])


if __name__ == "__main__":
    unittest.main()
