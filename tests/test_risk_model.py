import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.risk_model import LogisticRiskPredictor, train_logistic_risk_models


def row(urgency: float, insufficient: float, failure: bool):
    return {
        "status": "ok",
        "configuration": "C1",
        "query_features": {
            "token_count": 10,
            "character_count": 10,
            "has_question_mark": 1,
            "urgency_term_count": urgency,
            "hazard_term_count": urgency,
            "context_term_count": 1,
            "negation_count": 0,
            "multi_intent_connector_count": 0,
            "has_numeric_detail": 0,
            "surface_insufficient_information": insufficient,
        },
        "adjudication": {"severe_failure": failure},
    }


class RiskModelTests(unittest.TestCase):
    def test_trained_model_ranks_failure_higher(self):
        rows = [row(0, 0, False)] * 20 + [row(2, 1, True)] * 20
        model = train_logistic_risk_models(rows, iterations=300)
        predictor = LogisticRiskPredictor(model)
        low = dict(rows[0]["query_features"])
        high = dict(rows[-1]["query_features"])
        self.assertLess(
            predictor.predict_features(low, "C1"),
            predictor.predict_features(high, "C1"),
        )

    def test_new_protocol_labels_train_separate_heads(self):
        low = row(0, 0, False)
        high = row(2, 1, True)
        low["adjudication"].update(
            {"y_trigger": False, "y_miss": False, "y_quality": True}
        )
        high["adjudication"].update(
            {"y_trigger": True, "y_miss": True, "y_quality": False}
        )
        model = train_logistic_risk_models([low] * 20 + [high] * 20, iterations=200)
        self.assertTrue(
            {"trigger", "miss", "quality_failure", "combined_risk"}
            <= set(model["heads"])
        )
        scores = LogisticRiskPredictor(model).predict_feature_heads(
            high["query_features"], "C1"
        )
        self.assertIn("trigger", scores)


if __name__ == "__main__":
    unittest.main()
