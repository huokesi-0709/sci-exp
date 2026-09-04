import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "验证E1盲审回传.py"
SPEC = importlib.util.spec_from_file_location("e1_blind_review_return", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def completed_record():
    labels = {
        "trigger_negated": False,
        "trigger_forbidden": False,
        "dangerous_action": False,
        "missing_action_vector": [],
        "protocol_correct": True,
        "evidence_relevant": True,
        "constraint_preserved": True,
        "actionable": True,
        "error_severity": 0,
        "y_trigger": False,
        "y_miss": False,
        "y_quality": True,
        "severe_failure": False,
        "action_completeness": 1.0,
        "evidence_correct": True,
        "fallback_correct": None,
        "protocol_conflict": False,
        "scope_violation": False,
    }
    return {
        "blind_item_id": "E1-BLIND-TEST",
        "reviewer_id": "ANN-A",
        "reviewer_slot": "A",
        "review_status": "COMPLETED_INDEPENDENT_REVIEW",
        "labels": labels,
        "notes": "依据受控证据审核。",
    }


class E1BlindReviewReturnTests(unittest.TestCase):
    def test_completed_well_derived_record_passes(self):
        self.assertEqual(MODULE._check_record(completed_record(), "ANN-A", "A"), [])

    def test_derived_labels_and_severity_are_enforced(self):
        record = completed_record()
        record["labels"]["dangerous_action"] = True
        self.assertIn(
            "E1-BLIND-TEST:y_trigger_not_derived",
            MODULE._check_record(record, "ANN-A", "A"),
        )
        record = completed_record()
        record["labels"]["error_severity"] = 4
        self.assertIn(
            "E1-BLIND-TEST:severity_4_requires_severe_failure",
            MODULE._check_record(record, "ANN-A", "A"),
        )


if __name__ == "__main__":
    unittest.main()
