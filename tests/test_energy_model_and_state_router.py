import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.energy_model import EnergyPredictor, build_static_energy_table
from sci_exp.router import SafetyConstrainedRouter, SoftWeightingRouter
from sci_exp.schemas import QueryRecord


def query() -> QueryRecord:
    return QueryRecord(
        query_id="q1",
        text="发生地震后应该怎么办？",
        disaster_type="earthquake",
        query_type="single_action",
        risk_level=2,
        language="zh",
        should_fallback=False,
        source_group_id="g1",
    )


class AlwaysSafe:
    def predict(self, _query, _configuration):
        return 0.01


class StateEnergy:
    def predict(self, _features, configuration, state=None):
        hot = bool(state and float(state.get("device_temperature_c_start", 0)) > 70)
        if hot:
            return {"C0": 3.0, "C1": 1.0, "C2": 5.0}[configuration]
        return {"C0": 1.0, "C1": 2.0, "C2": 5.0}[configuration]


class EnergyModelTests(unittest.TestCase):
    def test_static_table_uses_only_valid_physical_energy(self):
        rows = [
            {"configuration": "C0", "telemetry": {"energy_j": 1.0, "external_meter_valid": True}},
            {"configuration": "C0", "telemetry": {"energy_j": 3.0, "external_meter_valid": True}},
            {"configuration": "C1", "telemetry": {"energy_j": 2.0, "external_meter_valid": False}},
        ]
        self.assertEqual(build_static_energy_table(rows), {"C0": 2.0})

    def test_state_aware_energy_changes_selection(self):
        router = SafetyConstrainedRouter(
            thresholds={"C0": 0.1, "C1": 0.1, "C2": 0.1},
            predicted_energy_j={"C0": 1, "C1": 2, "C2": 5},
            predicted_latency_ms={"C0": 1, "C1": 1, "C2": 1},
            predicted_memory_mb={"C0": 100, "C1": 100, "C2": 100},
            memory_budget_mb=1000,
            latency_budget_ms=1000,
            risk_predictor=AlwaysSafe(),
            energy_predictor=StateEnergy(),
        )
        self.assertEqual(router.select(query(), {"device_temperature_c_start": 30}).configuration, "C0")
        self.assertEqual(router.select(query(), {"device_temperature_c_start": 80}).configuration, "C1")

    def test_energy_budget_and_memory_headroom_can_force_fallback(self):
        router = SafetyConstrainedRouter(
            thresholds={"C0": 0.1, "C1": 0.1, "C2": 0.1},
            predicted_energy_j={"C0": 2, "C1": 3, "C2": 5},
            predicted_latency_ms={"C0": 1, "C1": 1, "C2": 1},
            predicted_memory_mb={"C0": 500, "C1": 700, "C2": 900},
            memory_budget_mb=1000,
            latency_budget_ms=1000,
            risk_predictor=AlwaysSafe(),
            energy_budget_j=1.0,
        )
        decision = router.select(query(), {"available_memory_mb_min": 600})
        self.assertEqual(decision.configuration, "C3")
        self.assertEqual(decision.effective_memory_budget_mb, 540.0)

    def test_soft_weighting_is_not_a_hard_safety_router(self):
        class Risk:
            def predict(self, _query, configuration):
                return {"C0": 0.20, "C1": 0.05, "C2": 0.01}[configuration]

        base = SafetyConstrainedRouter(
            thresholds={"C0": 0.1, "C1": 0.1, "C2": 0.1},
            predicted_energy_j={"C0": 1, "C1": 3, "C2": 5},
            predicted_latency_ms={"C0": 1, "C1": 1, "C2": 1},
            predicted_memory_mb={"C0": 100, "C1": 100, "C2": 100},
            memory_budget_mb=1000,
            latency_budget_ms=1000,
            risk_predictor=Risk(),
        )
        hard = base.select(query())
        soft = SoftWeightingRouter(base, risk_weight=0.2).select(query())
        self.assertEqual(hard.configuration, "C1")
        self.assertEqual(soft.configuration, "C0")


if __name__ == "__main__":
    unittest.main()
