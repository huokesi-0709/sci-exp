import argparse
import importlib.util
import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.cli import _send_collector_stop
from sci_exp.telemetry import TelemetrySampler


ROOT = Path(__file__).resolve().parents[1]


def load_energy_module():
    path = ROOT / "scripts" / "整合INA226查询能耗.py"
    spec = importlib.util.spec_from_file_location("ina226_energy", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_collector_module():
    path = ROOT / "scripts" / "采集INA226串口功率.py"
    spec = importlib.util.spec_from_file_location("ina226_collector", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Ina226PowerChainTests(unittest.TestCase):
    def test_collector_stop_marker_requires_explicit_opt_in(self):
        module = load_collector_module()
        self.assertFalse(module.is_stop_marker("collector_stop", ""))
        self.assertFalse(module.is_stop_marker("query_end", "collector_stop"))
        self.assertTrue(module.is_stop_marker("collector_stop", "collector_stop"))

    def test_cli_collector_stop_waits_for_stopping_ack(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]

        def acknowledge():
            packet, address = server.recvfrom(4096)
            value = json.loads(packet.decode("utf-8"))
            server.sendto(
                json.dumps(
                    {
                        "type": "marker_ack",
                        "event": value["event"],
                        "run_key": value["run_key"],
                        "collector_stopping": True,
                    }
                ).encode("utf-8"),
                address,
            )

        thread = threading.Thread(target=acknowledge)
        thread.start()
        result = _send_collector_stop(
            argparse.Namespace(
                collector_host="127.0.0.1",
                collector_port=port,
                collector_stop_timeout=1.0,
                collector_stop_retries=1,
                session_id="E1-TEST-STOP-001",
            )
        )
        thread.join(timeout=2)
        server.close()
        self.assertEqual(result["status"], "acknowledged")
        self.assertEqual(result["event"], "collector_stop")
        self.assertEqual(result["run_key"], "E1-TEST-STOP-001")

    def test_trapezoid_integration(self):
        module = load_energy_module()
        samples = [
            {"host_monotonic_ns": 0, "power_w": 2.0},
            {"host_monotonic_ns": 1_000_000_000, "power_w": 4.0},
            {"host_monotonic_ns": 2_000_000_000, "power_w": 2.0},
        ]
        energy, gap_ms = module.integrate(samples)
        self.assertAlmostEqual(energy, 6.0)
        self.assertEqual(gap_ms, 1000.0)

    def test_device_clock_is_used_after_host_marker_selection(self):
        module = load_energy_module()
        samples = [
            {
                "host_monotonic_ns": 0,
                "device_us": 0,
                "power_w": 2.0,
            },
            {
                # Delayed Windows serial delivery must not inflate measured
                # energy or invalidate an otherwise continuous INA226 stream.
                "host_monotonic_ns": 32_000_000,
                "device_us": 10_000,
                "power_w": 4.0,
            },
        ]
        energy, gap_ms = module.integrate(samples)
        self.assertAlmostEqual(energy, 0.03)
        self.assertEqual(gap_ms, 10.0)
        self.assertEqual(module.sample_timing(samples)[0], "device_us")
        self.assertEqual(module.maximum_host_arrival_gap_ms(samples), 32.0)

    def test_external_marker_requires_matching_ack(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]

        def acknowledge():
            packet, address = server.recvfrom(4096)
            value = json.loads(packet.decode("utf-8"))
            server.sendto(
                json.dumps(
                    {
                        "type": "marker_ack",
                        "event": value["event"],
                        "run_key": value["run_key"],
                    }
                ).encode("utf-8"),
                address,
            )

        thread = threading.Thread(target=acknowledge)
        thread.start()
        sampler = TelemetrySampler(
            external_marker_host="127.0.0.1",
            external_marker_port=port,
        )
        sampler.mark("query_start", {"run_key": "q:C1:0"})
        thread.join(timeout=2)
        server.close()
        self.assertEqual(sampler.external_markers_sent, 1)
        self.assertFalse(sampler.external_marker_errors)
        self.assertEqual(len(sampler.external_marker_rtt_ms), 1)

    def test_environment_summary_and_external_energy_merge(self):
        module = load_energy_module()
        summary = module.summarize_environment(
            [
                {
                    "valid": True,
                    "ambient_temperature_c": 24.0,
                    "ambient_relative_humidity_pct": 50.0,
                },
                {
                    "valid": True,
                    "ambient_temperature_c": 26.0,
                    "ambient_relative_humidity_pct": 54.0,
                },
            ]
        )
        self.assertEqual(summary["ambient_temperature_c_mean"], 25.0)
        merged = module.merge_energy_into_runs(
            [{"run_key": "q:C1:0", "telemetry": {"energy_j": None}}],
            [
                {
                    "run_key": "q:C1:0",
                    "valid": True,
                    "energy_j": 3.5,
                    "sample_count": 100,
                    "maximum_sample_gap_ms": 11.0,
                    "flags": {},
                    **summary,
                }
            ],
        )
        self.assertEqual(merged[0]["telemetry"]["energy_j"], 3.5)
        self.assertEqual(
            merged[0]["telemetry"]["ambient_temperature_c_mean"], 25.0
        )

    def test_idle_power_is_estimated_from_marked_interval(self):
        module = load_energy_module()
        samples = [
            {"host_monotonic_ns": 0, "power_w": 2.0},
            {"host_monotonic_ns": 1_000_000_000, "power_w": 2.0},
            {"host_monotonic_ns": 2_000_000_000, "power_w": 2.0},
        ]
        markers = [
            {"event": "idle_start", "run_key": "idle", "host_monotonic_ns": 0},
            {
                "event": "idle_end",
                "run_key": "idle",
                "host_monotonic_ns": 2_000_000_000,
            },
        ]
        power, details = module.estimate_idle_power(samples, markers)
        self.assertEqual(power, 2.0)
        self.assertEqual(details["interval_count"], 1)

    def test_measurement_card_and_firmware_exist(self):
        self.assertTrue(
            (
                ROOT
                / "hardware"
                / "esp32s3_ina226_power_meter"
                / "src"
                / "main.cpp"
            ).is_file()
        )
        self.assertTrue(
            (ROOT / "docs" / "INA226物理功率测量卡_v1.0.md").is_file()
        )


if __name__ == "__main__":
    unittest.main()
