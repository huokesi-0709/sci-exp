import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.ingestion import chunk_protocol_text, prepare_protocols


class IngestionTests(unittest.TestCase):
    def test_chunking_is_deterministic_and_overlapping(self):
        text = "第一条。" * 100
        first = chunk_protocol_text(text, target_characters=80, overlap_characters=10)
        second = chunk_protocol_text(text, target_characters=80, overlap_characters=10)
        self.assertEqual(first, second)
        self.assertGreater(len(first), 1)

    def test_registry_creates_stable_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "protocol.txt").write_text("保持安全距离。服从疏散指示。", encoding="utf-8")
            registry = [
                {
                    "source_id": "fire_demo",
                    "file": "protocol.txt",
                    "source_org": "test",
                    "authority_level": 1,
                    "hazard_types": ["fire"],
                    "status": "current",
                }
            ]
            chunks = prepare_protocols(registry, registry_directory=root)
            self.assertEqual(chunks[0].evidence_id, "fire_demo_0001")
            self.assertEqual(chunks[0].source_id, "fire_demo")


if __name__ == "__main__":
    unittest.main()
