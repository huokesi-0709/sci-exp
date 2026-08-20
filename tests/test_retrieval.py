import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.retrieval import BM25Index
from sci_exp.schemas import ProtocolChunk


class RetrievalTests(unittest.TestCase):
    def test_chinese_query_retrieves_relevant_protocol(self):
        chunks = [
            ProtocolChunk("fire", "室内烟雾时保持低姿撤离，不得使用电梯。", "test"),
            ProtocolChunk("flood", "积水道路不要驾车进入。", "test"),
        ]
        results = BM25Index(chunks).search("烟雾怎么撤离", top_k=1)
        self.assertEqual(results[0].chunk.evidence_id, "fire")
        self.assertGreater(results[0].score, 0)


if __name__ == "__main__":
    unittest.main()
