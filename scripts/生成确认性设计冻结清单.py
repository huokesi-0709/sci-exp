from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ASSETS = (
    "docs/研究协议_v2.0_确认性设计冻结.md",
    "docs/主要终点与假设表_v2.0.csv",
    "docs/设备与软件环境锁定表_v1.0.yaml",
    "docs/研究资产版本命名规则_v1.0.md",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="生成确认性设计冻结资产的哈希清单。")
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    assets = {}
    for relative in ASSETS:
        path = root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        assets[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    result = {
        "manifest_version": "v2.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_version": "2.0.0",
        "design_frozen": True,
        "formal_test_results_seen": False,
        "current_400_status": "development_gold_not_confirmatory_cal_or_test",
        "planned_core_queries": 3600,
        "planned_test_op_queries": 1200,
        "primary_comparison": "PROPOSED_vs_fixed_C2",
        "primary_endpoint": "paired_L3_severe_failure",
        "hardware_identity_status": "blocked_pending_radxa_probe",
        "assets": assets,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"assets": len(assets), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
