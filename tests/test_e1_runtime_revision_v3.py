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


if __name__ == "__main__":
    unittest.main()
