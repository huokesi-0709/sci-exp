import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.calibration import select_threshold


class CalibrationTests(unittest.TestCase):
    def test_selects_largest_safe_coverage(self):
        rows = [(0.1, False)] * 100 + [(0.9, True)] * 10
        result = select_threshold(rows, alpha=0.05, delta=0.05)
        self.assertEqual(result.threshold, 0.1)
        self.assertEqual(result.accepted, 100)
        self.assertLessEqual(result.upper_risk, 0.05)


if __name__ == "__main__":
    unittest.main()
