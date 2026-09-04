import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "生成E1盲法双审材料.py"
)
SPEC = importlib.util.spec_from_file_location("e1_blind_review", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class E1BlindReviewTests(unittest.TestCase):
    def test_blind_id_is_stable_and_secret_dependent(self):
        first = MODULE._blind_id(b"a" * 32, "formal_exp_0001:C0:0")
        second = MODULE._blind_id(b"a" * 32, "formal_exp_0001:C0:0")
        changed = MODULE._blind_id(b"b" * 32, "formal_exp_0001:C0:0")
        self.assertEqual(first, second)
        self.assertNotEqual(first, changed)
        self.assertRegex(first, r"^E1-BLIND-[0-9A-F]{20}$")

    def test_blind_review_asset_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "review.jsonl"
            MODULE._write_jsonl_new(path, [{"blind_item_id": "E1-BLIND-TEST"}])
            with self.assertRaises(FileExistsError):
                MODULE._write_jsonl_new(
                    path,
                    [{"blind_item_id": "E1-BLIND-REPLACEMENT"}],
                )

    def test_reviewer_and_adjudicator_ids_must_be_distinct(self):
        self.assertEqual(
            MODULE._validate_reviewer_ids("E1-REV-A-01", "E1-REV-B-01", "E1-ADJ-01"),
            ("E1-REV-A-01", "E1-REV-B-01", "E1-ADJ-01"),
        )
        with self.assertRaises(ValueError):
            MODULE._validate_reviewer_ids("E1-REV-A-01", "E1-REV-A-01", "E1-ADJ-01")

    def test_full_package_contains_315_blinded_items_and_refuses_rerun(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.jsonl"
            queries = root / "queries.jsonl"
            runs = root / "runs.jsonl"
            salt = root / "private_salt.bin"
            output = root / "review"
            query_rows = [
                {"query_id": f"q{index:02d}", "text": f"问题{index}"}
                for index in range(35)
            ]
            manifest_rows = []
            run_rows = []
            for run_order in range(1, 316):
                query_id = f"q{(run_order - 1) % 35:02d}"
                configuration = ("C0", "C1", "C2")[(run_order - 1) % 3]
                repetition = (run_order - 1) // 105
                run_key = f"{query_id}:{configuration}:{run_order}"
                manifest_rows.append(
                    {
                        "run_order": run_order,
                        "run_key": run_key,
                        "query_id": query_id,
                        "configuration": configuration,
                        "repetition": repetition,
                    }
                )
                run_rows.append(
                    {
                        "run_key": run_key,
                        "status": "ok",
                        "answer": f"回答{run_order}",
                        "evidence": [],
                        "evidence_ids": [],
                        "fallback": False,
                        "fallback_reason": None,
                        "telemetry": {"external_meter_valid": True},
                    }
                )

            for path, rows in (
                (manifest, manifest_rows),
                (queries, query_rows),
                (runs, run_rows),
            ):
                path.write_text(
                    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
                    encoding="utf-8",
                )
            salt.write_bytes(b"s" * 32)
            arguments = [
                str(SCRIPT_PATH),
                "--manifest",
                str(manifest),
                "--queries",
                str(queries),
                "--runs",
                str(runs),
                "--blind-salt-file",
                str(salt),
                "--output-directory",
                str(output),
                "--reviewer-a-id",
                "E1-REV-A-01",
                "--reviewer-b-id",
                "E1-REV-B-01",
                "--adjudicator-id",
                "E1-ADJ-01",
            ]
            with patch.object(sys, "argv", arguments), redirect_stdout(io.StringIO()):
                self.assertEqual(MODULE.main(), 0)

            reviewer_a = MODULE._read_jsonl(
                output / "reviewer_A" / "E1_review_A.jsonl"
            )
            reviewer_b = MODULE._read_jsonl(
                output / "reviewer_B" / "E1_review_B.jsonl"
            )
            self.assertEqual(len(reviewer_a), 315)
            self.assertEqual(len(reviewer_b), 315)
            self.assertTrue(
                all(row["reviewer_id"] == "E1-REV-A-01" for row in reviewer_a)
            )
            self.assertTrue(
                all(row["reviewer_id"] == "E1-REV-B-01" for row in reviewer_b)
            )
            self.assertEqual(
                {row["blind_item_id"] for row in reviewer_a},
                {row["blind_item_id"] for row in reviewer_b},
            )
            self.assertNotEqual(
                [row["blind_item_id"] for row in reviewer_a],
                [row["blind_item_id"] for row in reviewer_b],
            )
            self.assertTrue(
                all(
                    field not in reviewer_a[0]
                    for field in ("configuration", "repetition", "run_key")
                )
            )
            with patch.object(sys, "argv", arguments), redirect_stdout(io.StringIO()):
                with self.assertRaises(FileExistsError):
                    MODULE.main()


if __name__ == "__main__":
    unittest.main()
