import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.runner import (
    build_exhaustive_task_manifest_rows,
    run_exhaustive,
)
from sci_exp.schemas import InferenceQuery


class E1FormalManifestTests(unittest.TestCase):
    def _config(self, root: Path):
        return {
            "_project_root": str(root),
            "experiment": {
                "configs": ["C0", "C1"],
                "repetitions": 2,
                "seed": 42,
                "output": "results/default.jsonl",
            },
            "telemetry": {},
        }

    def _queries(self):
        return [
            InferenceQuery("q1", "问题1", "zh", "g1", "valid"),
            InferenceQuery("q2", "问题2", "zh", "g2", "valid"),
        ]

    def test_manifest_is_unique_contiguous_and_deterministic(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self._config(Path(temporary))
            first = build_exhaustive_task_manifest_rows(config, self._queries())
            second = build_exhaustive_task_manifest_rows(config, self._queries())
        self.assertEqual(first, second)
        self.assertEqual(len(first), 8)
        self.assertEqual([row["run_order"] for row in first], list(range(1, 9)))
        self.assertEqual(len({row["run_key"] for row in first}), 8)

    def test_formal_slice_keeps_global_order_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self._config(root)
            rows = build_exhaustive_task_manifest_rows(config, self._queries())
            manifest = root / "manifest.jsonl"
            manifest.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            output = root / "results" / "batch.jsonl"

            def fake_run_one(_pipeline, query, configuration, repetition, _telemetry, **kwargs):
                return {
                    "status": "ok",
                    "query_id": query.query_id,
                    "configuration": configuration,
                    "repetition": repetition,
                    "run_order": kwargs["run_order"],
                    "session_id": kwargs["session_id"],
                }

            with patch("sci_exp.runner.build_pipeline", return_value=object()), patch(
                "sci_exp.runner._run_one", side_effect=fake_run_one
            ):
                result = run_exhaustive(
                    config,
                    [],
                    self._queries(),
                    output_path=output,
                    task_manifest_path=manifest,
                    run_order_start=2,
                    run_order_end=4,
                    session_id="E1-FORMAL-B01",
                )
                self.assertEqual([row["run_order"] for row in result], [2, 3, 4])
                persisted = [
                    json.loads(line)
                    for line in output.read_text(encoding="utf-8").splitlines()
                ]
                self.assertEqual([row["run_order"] for row in persisted], [2, 3, 4])
                self.assertTrue(
                    all(row["formal_execution"]["global_run_count"] == 8 for row in result)
                )
                with self.assertRaises(FileExistsError):
                    run_exhaustive(
                        config,
                        [],
                        self._queries(),
                        output_path=output,
                        task_manifest_path=manifest,
                        run_order_start=2,
                        run_order_end=4,
                        session_id="E1-FORMAL-B01",
                    )

    def test_interrupted_formal_batch_preserves_completed_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self._config(root)
            rows = build_exhaustive_task_manifest_rows(config, self._queries())
            manifest = root / "manifest.jsonl"
            manifest.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            output = root / "results" / "interrupted.jsonl"
            calls = 0

            def interrupt_after_first(
                _pipeline, query, configuration, repetition, _telemetry, **kwargs
            ):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise KeyboardInterrupt()
                return {
                    "status": "ok",
                    "query_id": query.query_id,
                    "configuration": configuration,
                    "repetition": repetition,
                    "run_order": kwargs["run_order"],
                }

            with patch("sci_exp.runner.build_pipeline", return_value=object()), patch(
                "sci_exp.runner._run_one", side_effect=interrupt_after_first
            ):
                with self.assertRaises(KeyboardInterrupt):
                    run_exhaustive(
                        config,
                        [],
                        self._queries(),
                        output_path=output,
                        task_manifest_path=manifest,
                        run_order_start=1,
                        run_order_end=3,
                        session_id="E1-FORMAL-INTERRUPTED",
                    )
            persisted = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(persisted), 1)
            self.assertEqual(persisted[0]["run_order"], 1)

    def test_manifest_order_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self._config(root)
            rows = build_exhaustive_task_manifest_rows(config, self._queries())
            rows[0], rows[1] = rows[1], rows[0]
            manifest = root / "bad.jsonl"
            manifest.write_text(
                "".join(json.dumps(row) + "\n" for row in rows),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "differs from seeded runner order"):
                run_exhaustive(
                    config,
                    [],
                    self._queries(),
                    output_path=root / "out.jsonl",
                    task_manifest_path=manifest,
                    session_id="E1-FORMAL-B01",
                )


if __name__ == "__main__":
    unittest.main()
