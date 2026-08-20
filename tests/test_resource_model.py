import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.resource_model import build_resource_profile


class ResourceModelTests(unittest.TestCase):
    def test_requires_physical_energy_by_default(self):
        rows = [
            {
                "status": "ok",
                "configuration": "C1",
                "latency_ms": 10,
                "telemetry": {"energy_j": None, "process_peak_rss_mb": 100},
            }
        ]
        with self.assertRaises(ValueError):
            build_resource_profile(rows)
        profile = build_resource_profile(rows, require_energy=False)
        self.assertEqual(profile["predicted_latency_ms"]["C1"], 10)


if __name__ == "__main__":
    unittest.main()
