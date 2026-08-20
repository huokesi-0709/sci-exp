import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.schemas import QueryRecord
from sci_exp.splitting import group_split
from sci_exp.validation import validate_no_group_leakage


def make_query(query_id: str, group: str) -> QueryRecord:
    return QueryRecord(
        query_id=query_id,
        text="test",
        disaster_type="general",
        query_type="test",
        risk_level=1,
        language="en",
        should_fallback=False,
        source_group_id=group,
    )


class SplittingTests(unittest.TestCase):
    def test_group_never_crosses_splits(self):
        queries = [
            make_query("a1", "a"),
            make_query("a2", "a"),
            make_query("b1", "b"),
        ]
        split = group_split(queries)
        self.assertEqual(validate_no_group_leakage(split), [])
        self.assertEqual(split[0].split, split[1].split)


if __name__ == "__main__":
    unittest.main()
