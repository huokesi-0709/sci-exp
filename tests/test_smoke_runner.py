import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.config import load_config
from sci_exp.io_utils import read_jsonl
from sci_exp.runner import run_exhaustive, run_routed
from sci_exp.schemas import ProtocolChunk, QueryRecord


class SmokeRunnerTests(unittest.TestCase):
    def test_all_four_configurations_run(self):
        root = Path(__file__).resolve().parents[1]
        config = load_config(root / "configs" / "windows.smoke.json")
        protocols = [
            ProtocolChunk.from_dict(row)
            for row in read_jsonl(root / "data" / "processed" / "sample_protocols.jsonl")
        ]
        queries = [
            QueryRecord.from_dict(row)
            for row in read_jsonl(root / "data" / "processed" / "sample_queries.jsonl")
        ]
        with tempfile.TemporaryDirectory() as temporary:
            rows = run_exhaustive(
                config,
                protocols,
                queries[:1],
                output_path=Path(temporary) / "runs.jsonl",
            )
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["status"] == "ok" for row in rows))
        self.assertEqual({row["configuration"] for row in rows}, {"C0", "C1", "C2", "C3"})

    def test_routing_is_inside_measured_window(self):
        root = Path(__file__).resolve().parents[1]
        config = load_config(root / "configs" / "windows.smoke.json")
        protocols = [
            ProtocolChunk.from_dict(row)
            for row in read_jsonl(root / "data" / "processed" / "sample_protocols.jsonl")
        ]
        queries = [
            QueryRecord.from_dict(row)
            for row in read_jsonl(root / "data" / "processed" / "sample_queries.jsonl")
        ]
        with tempfile.TemporaryDirectory() as temporary:
            rows = run_routed(
                config,
                protocols,
                queries[:1],
                output_path=Path(temporary) / "routed.jsonl",
            )
        self.assertIn("routing", rows[0])
        self.assertGreaterEqual(rows[0]["routing_overhead_ms"], 0.0)
        self.assertIn(":ROUTED:", rows[0]["run_key"])


if __name__ == "__main__":
    unittest.main()
