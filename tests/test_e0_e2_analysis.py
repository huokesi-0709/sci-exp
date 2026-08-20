import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, filename: str):
    path = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ExperimentAnalysisTests(unittest.TestCase):
    def test_e0_effective_rate_and_sequence(self):
        module = load_script("e0_analysis", "分析E0功率测量链.py")
        samples = [
            {
                "host_monotonic_ns": index * 10_000_000,
                "power_w": 2.0,
                "seq": index,
                "current_saturated": False,
                "shunt_near_limit": False,
                "undervoltage": False,
                "integration_gap": False,
            }
            for index in range(101)
        ]
        quality = module.sample_quality(samples, 100.0)
        self.assertAlmostEqual(quality["effective_sample_rate_hz"], 100.0)
        self.assertEqual(quality["sequence_missing_samples"], 0)
        self.assertEqual(quality["gap_ms_max"], 10.0)
        self.assertEqual(quality["dropout_fraction"], 0.0)

    def test_sync_request_timestamp_is_preserved(self):
        module = load_script("collector", "采集INA226串口功率.py")
        value = module.add_host_time(
            {"type": "sync_ack", "host_epoch_ns": "123", "device_us": 456}
        )
        self.assertEqual(value["sync_request_epoch_ns"], "123")
        self.assertNotEqual(value["host_epoch_ns"], "123")

    def test_e2_uar_and_ser_definitions(self):
        module = load_script("e2_analysis", "分析E2安全校准.py")
        result = module.metrics([1, 1, 0, 0], [0.9, 0.2, 0.1, 0.3], 0.25)
        self.assertEqual(result["recall"], 0.5)
        self.assertEqual(result["uar_unsafe_acceptance_rate"], 0.5)
        self.assertEqual(result["ser_safety_error_among_accepted"], 0.5)


if __name__ == "__main__":
    unittest.main()
