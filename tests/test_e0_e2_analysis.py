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
        self.assertEqual(quality["dropout_source"], "sequence")
        self.assertEqual(quality["timing_source"], "host_monotonic_ns")

    def test_e0_prefers_device_clock_over_quantized_host_clock(self):
        module = load_script("e0_device_clock", "分析E0功率测量链.py")
        samples = [
            {
                "device_us": index * 10_000,
                "host_monotonic_ns": (index // 2) * 20_000_000,
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
        self.assertEqual(quality["timing_source"], "device_us")
        self.assertAlmostEqual(quality["effective_sample_rate_hz"], 100.0)
        self.assertEqual(quality["gap_ms_max"], 10.0)
        self.assertEqual(quality["dropout_fraction"], 0.0)

    def test_e0_dropout_uses_missing_sequence_numbers(self):
        module = load_script("e0_sequence_dropout", "分析E0功率测量链.py")
        samples = [
            {
                "device_us": device_us,
                "host_monotonic_ns": device_us * 1_000,
                "power_w": 2.0,
                "seq": seq,
                "current_saturated": False,
                "shunt_near_limit": False,
                "undervoltage": False,
                "integration_gap": False,
            }
            for seq, device_us in ((0, 0), (1, 10_000), (3, 30_000))
        ]
        quality = module.sample_quality(samples, 100.0)
        self.assertEqual(quality["sequence_missing_samples"], 1)
        self.assertEqual(quality["dropout_source"], "sequence")
        self.assertAlmostEqual(quality["dropout_fraction"], 0.25)

    def test_e0_idle_gate_counts_only_intervals_at_least_60_seconds(self):
        module = load_script("e0_idle_duration", "分析E0功率测量链.py")
        markers = []
        samples = []
        for index, duration_s in enumerate((9.0, 60.0, 61.0, 65.0), 1):
            key = f"idle_{index}"
            start_ns = index * 100_000_000_000
            end_ns = start_ns + int(duration_s * 1_000_000_000)
            markers.extend(
                [
                    {"event": "idle_start", "run_key": key, "host_monotonic_ns": start_ns},
                    {"event": "idle_end", "run_key": key, "host_monotonic_ns": end_ns},
                ]
            )
            samples.extend(
                [
                    {"host_monotonic_ns": start_ns, "power_w": 1.0},
                    {"host_monotonic_ns": end_ns, "power_w": 1.0},
                ]
            )
        idle = module.idle_quality(samples, markers, 60.0)
        self.assertEqual(idle["interval_count"], 4)
        self.assertEqual(idle["qualifying_interval_count"], 3)

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
