from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        telemetry = row.get("telemetry") or {}
        energy = telemetry.get("energy_j")
        if row.get("status") == "ok" and energy is not None and telemetry.get("external_meter_valid") is not False:
            grouped[str(row.get("configuration", ""))].append(row)
    result = {}
    for configuration, values in sorted(grouped.items()):
        energies = [float(row["telemetry"]["energy_j"]) for row in values]
        latencies = [float(row["latency_ms"]) for row in values]
        result[configuration] = {
            "n": len(values),
            "energy_j_mean": statistics.mean(energies),
            "energy_j_median": statistics.median(energies),
            "latency_ms_mean": statistics.mean(latencies),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="E7同配置库跨设备画像比较")
    parser.add_argument("--device", action="append", required=True, help="NAME=RUNS.jsonl")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    devices = {}
    for spec in args.device:
        if "=" not in spec:
            raise SystemExit("--device格式必须为NAME=PATH")
        name, path = spec.split("=", 1)
        devices[name] = summarize(read_rows(Path(path)))
    report = {
        "schema_version": "e7-cross-device-v1.0",
        "devices": devices,
        "recalibration_required": True,
        "interpretation": "跨设备只共享配置语义和安全模型候选；能耗模型、资源画像和阈值适用性必须重新检查，不能直接迁移Radxa成本表。",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"devices": list(devices), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
