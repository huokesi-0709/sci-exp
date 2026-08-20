import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.router import SafetyConstrainedRouter
from sci_exp.features import query_features
from sci_exp.schemas import QueryRecord


def query(text: str, query_type: str, risk: int, disaster: str) -> QueryRecord:
    return QueryRecord(
        query_id="q",
        text=text,
        disaster_type=disaster,
        query_type=query_type,
        risk_level=risk,
        language="zh",
        should_fallback=query_type == "insufficient_information",
        source_group_id="g",
    )


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.router = SafetyConstrainedRouter(
            thresholds={"C0": 0.1, "C1": 0.1, "C2": 0.1},
            predicted_energy_j={"C0": 1, "C1": 2, "C2": 4, "C3": 0.2},
            predicted_latency_ms={"C0": 100, "C1": 200, "C2": 300, "C3": 10},
            memory_budget_mb=4096,
            latency_budget_ms=5000,
        )

    def test_selects_safe_configuration(self):
        decision = self.router.select(
            query("厨房起火还有浓烟，我在二楼应该从哪里撤离？", "single_action", 3, "fire")
        )
        self.assertEqual(decision.configuration, "C2")

    def test_falls_back_when_context_is_insufficient(self):
        decision = self.router.select(
            query("怎么办？", "insufficient_information", 2, "general")
        )
        self.assertEqual(decision.configuration, "C3")

    def test_inference_features_exclude_gold_labels(self):
        features = query_features(
            query("厨房起火怎么办？", "single_action", 3, "fire")
        )
        forbidden = {
            "risk_level",
            "query_type",
            "should_fallback",
            "disaster_type",
            "gold_evidence_ids",
        }
        self.assertFalse(forbidden & features.keys())

    def test_multi_head_thresholds_are_all_hard_constraints(self):
        class Predictor:
            def predict(self, _query, _configuration):
                return 0.01

            def predict_heads(self, _query, configuration):
                return {
                    "trigger": 0.01,
                    "miss": 0.20 if configuration == "C0" else 0.01,
                    "quality_failure": 0.01,
                }

        router = SafetyConstrainedRouter(
            thresholds={
                "trigger": {"C0": 0.1, "C1": 0.1, "C2": 0.1},
                "miss": {"C0": 0.1, "C1": 0.1, "C2": 0.1},
                "quality_failure": {"C0": 0.1, "C1": 0.1, "C2": 0.1},
            },
            predicted_energy_j={"C0": 1, "C1": 2, "C2": 4},
            predicted_latency_ms={"C0": 100, "C1": 200, "C2": 300},
            memory_budget_mb=4096,
            latency_budget_ms=5000,
            risk_predictor=Predictor(),
        )
        decision = router.select(query("有浓烟", "single_action", 3, "fire"))
        self.assertEqual(decision.configuration, "C1")
        self.assertNotIn("C0", decision.feasible_configurations)


if __name__ == "__main__":
    unittest.main()
