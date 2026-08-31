from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sci_exp.runner import build_exhaustive_task_manifest_rows
from sci_exp.schemas import InferenceQuery


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
        for row in rows
    )
    path.write_text(content, encoding="utf-8", newline="\n")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="冻结与sci_exp.runner完全一致的E1正式315次全局随机运行清单"
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--power-chain-lock", required=True)
    parser.add_argument("--runner-source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument(
        "--freeze-id", default="E1-DEVTEMP-FORMAL-SEED42-V1"
    )
    parser.add_argument("--frozen-on", default="2026-08-31")
    parser.add_argument("--batch-count", type=int, default=5)
    args = parser.parse_args()

    config_path = Path(args.config)
    queries_path = Path(args.queries)
    power_lock_path = Path(args.power_chain_lock)
    runner_source_path = Path(args.runner_source)
    output_path = Path(args.output)
    summary_path = Path(args.summary)
    existing = [path for path in (output_path, summary_path) if path.exists()]
    if existing:
        raise FileExistsError(
            "refusing to overwrite frozen E1 design asset: "
            + ", ".join(str(path) for path in existing)
        )

    config = _read_json(config_path)
    query_rows = _read_jsonl(queries_path)
    queries = [InferenceQuery.from_dict(row) for row in query_rows]
    if len(queries) != 35:
        raise ValueError(f"formal Dev-Temp must contain 35 queries, got {len(queries)}")
    if len({query.query_id for query in queries}) != len(queries):
        raise ValueError("query_id values are not unique")
    if {query.split for query in queries} != {"valid"}:
        raise ValueError("formal E1 manifest accepts only the Dev-Temp valid split")

    experiment = config.get("experiment", {})
    if int(experiment.get("seed", -1)) != 42:
        raise ValueError("formal E1 seed must remain 42")
    if int(experiment.get("repetitions", -1)) != 3:
        raise ValueError("formal E1 requires exactly 3 repetitions")
    if list(experiment.get("configs", [])) != ["C0", "C1", "C2"]:
        raise ValueError("formal E1 configuration order must be C0,C1,C2")

    rows = build_exhaustive_task_manifest_rows(config, queries)
    if len(rows) != 315:
        raise ValueError(f"formal task count must be 315, got {len(rows)}")
    if len({row["run_key"] for row in rows}) != 315:
        raise ValueError("run_key values are not unique")
    if [row["run_order"] for row in rows] != list(range(1, 316)):
        raise ValueError("run_order must be contiguous from 1 to 315")

    batch_count = int(args.batch_count)
    if batch_count < 1 or len(rows) % batch_count != 0:
        raise ValueError("batch count must divide 315 exactly")
    batch_size = len(rows) // batch_count
    batches = [
        {
            "batch_id": f"B{index:02d}",
            "run_order_start": (index - 1) * batch_size + 1,
            "run_order_end": index * batch_size,
            "run_count": batch_size,
            "output_pattern": f"results/E1_devtemp_formal_v1_B{index:02d}.jsonl",
            "collector_pattern": f"INA226_E1_devtemp_formal_v1_B{index:02d}.full.jsonl",
        }
        for index in range(1, batch_count + 1)
    ]

    _write_jsonl(output_path, rows)
    manifest_sha256 = _sha256(output_path)
    summary = {
        "schema_version": "e1-formal-run-freeze-v1.0",
        "freeze_id": args.freeze_id,
        "frozen_on": args.frozen_on,
        "formal_evidence": False,
        "role": "pre-registered Dev-Temp execution design; not an experiment result",
        "query_role": "Dev-Temp development_gold",
        "query_count": len(queries),
        "configurations": ["C0", "C1", "C2"],
        "repetitions_per_configuration": 3,
        "seed": 42,
        "total_runs": len(rows),
        "global_randomization": "Python random.Random(42).shuffle using sci_exp.runner task construction",
        "manifest": str(output_path).replace("\\", "/"),
        "manifest_sha256": manifest_sha256,
        "inputs": {
            "config": str(config_path).replace("\\", "/"),
            "config_sha256": _sha256(config_path),
            "queries": str(queries_path).replace("\\", "/"),
            "queries_sha256": _sha256(queries_path),
            "power_chain_lock": str(power_lock_path).replace("\\", "/"),
            "power_chain_lock_sha256": _sha256(power_lock_path),
            "runner_source": str(runner_source_path).replace("\\", "/"),
            "runner_source_sha256": _sha256(runner_source_path),
        },
        "batch_plan": batches,
        "batch_rule": "batches are contiguous slices of one frozen global order; never reshuffle within a batch",
        "overwrite_rule": "formal batch output paths are immutable and the CLI refuses an existing output",
        "acceptance_rule": "every run is retained; only external_meter_valid=true enters the valid physical-measurement subset",
        "review_rule": "every successful output requires independent blinded A/B review and adjudication before E1 analysis",
    }
    _write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
