from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _write_jsonl_new(path: Path, rows: list[dict[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite formal master: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _validate(task: dict[str, Any], row: dict[str, Any]) -> None:
    run_key = str(task["run_key"])
    if str(row.get("run_key", "")) != run_key:
        raise ValueError(f"run key mismatch for {run_key}")
    for field in ("query_id", "configuration", "repetition", "run_order"):
        if row.get(field) != task.get(field):
            raise ValueError(f"{field} mismatch for {run_key}")
    telemetry = row.get("telemetry") or {}
    energy = telemetry.get("energy_j")
    if row.get("status") != "ok" or telemetry.get("external_meter_valid") is not True:
        raise ValueError(f"not a valid physical result: {run_key}")
    if not isinstance(energy, (int, float)) or not math.isfinite(float(energy)) or energy < 0:
        raise ValueError(f"invalid energy_j for {run_key}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="将5个已接受E1物理能耗批次校验并固化为不可覆盖的315条主表"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--runs", required=True, action="append", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audit-output", required=True, type=Path)
    args = parser.parse_args()

    if args.output.exists() or args.audit_output.exists():
        existing = [str(path) for path in (args.output, args.audit_output) if path.exists()]
        raise FileExistsError("refusing to overwrite formal master asset: " + ", ".join(existing))

    manifest = _read_jsonl(args.manifest)
    if len(manifest) != 315:
        raise ValueError(f"manifest must contain exactly 315 rows, got {len(manifest)}")
    expected = {str(task.get("run_key", "")): task for task in manifest}
    if len(expected) != 315 or "" in expected:
        raise ValueError("manifest has duplicate or empty run_key")

    rows_by_key: dict[str, dict[str, Any]] = {}
    source_audit: list[dict[str, Any]] = []
    for source in args.runs:
        rows = _read_jsonl(source)
        source_audit.append(
            {
                "path": str(source).replace("\\", "/"),
                "rows": len(rows),
                "bytes": source.stat().st_size,
                "sha256": _sha256(source),
            }
        )
        for row in rows:
            run_key = str(row.get("run_key", ""))
            if not run_key or run_key in rows_by_key:
                raise ValueError(f"duplicate or empty run_key in source files: {run_key!r}")
            rows_by_key[run_key] = row

    missing = sorted(set(expected) - set(rows_by_key))
    extra = sorted(set(rows_by_key) - set(expected))
    if missing or extra:
        raise ValueError(f"manifest/source mismatch: missing={len(missing)}, extra={len(extra)}")

    ordered = []
    for task in sorted(manifest, key=lambda item: int(item["run_order"])):
        row = rows_by_key[str(task["run_key"])]
        _validate(task, row)
        ordered.append(row)

    _write_jsonl_new(args.output, ordered)
    audit = {
        "schema_version": "e1-formal-energy-master-audit-v1.0",
        "formal_evidence": True,
        "manifest": {
            "path": str(args.manifest).replace("\\", "/"),
            "rows": len(manifest),
            "sha256": _sha256(args.manifest),
        },
        "source_artifacts": source_audit,
        "output": {
            "path": str(args.output).replace("\\", "/"),
            "rows": len(ordered),
            "bytes": args.output.stat().st_size,
            "sha256": _sha256(args.output),
        },
        "validation": {
            "status_ok_count": sum(row.get("status") == "ok" for row in ordered),
            "external_meter_valid_count": sum(
                (row.get("telemetry") or {}).get("external_meter_valid") is True
                for row in ordered
            ),
            "configuration_counts": dict(Counter(str(row["configuration"]) for row in ordered)),
            "run_order_range": [ordered[0]["run_order"], ordered[-1]["run_order"]],
            "disposition": "eligible_input_to_frozen_blind_output_review_only",
        },
    }
    args.audit_output.parent.mkdir(parents=True, exist_ok=True)
    args.audit_output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
