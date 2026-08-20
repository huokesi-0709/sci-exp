from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_DATA = (
    "data/processed/protocols.jsonl",
    "data/splits_stratified_v2/train.jsonl",
    "data/splits_stratified_v2/valid.jsonl",
    "data/splits_stratified_v2/cal_op.jsonl",
    "data/splits_stratified_v2/cal_ch.jsonl",
    "data/splits_stratified_v2/test_op.jsonl",
    "data/splits_stratified_v2/test_ch.jsonl",
    "data/splits_stratified_v2/正式400条分层六分区清单_v2.0.json",
)
REQUIRED_CODE = (
    "configs/radxa.experiment.json",
    "configs/radxa.challenge.json",
    "scripts/setup_radxa.sh",
    "scripts/collect_device_info.sh",
    "scripts/detect_power_paths.sh",
    "scripts/start_llama_server.sh",
    "scripts/run_radxa_formal_tests.sh",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查复制到Radxa前的正式实验就绪状态。")
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def final_test_eligible(path: Path) -> bool:
    if not path.is_file():
        return False
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return bool(rows) and all(
        row.get("final_evaluation_eligible") is True
        and row.get("dataset_role") != "development_gold"
        for row in rows
    )


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()
    data_files = {
        rel: {
            "exists": (root / rel).is_file(),
            "sha256": sha256(root / rel) if (root / rel).is_file() else None,
        }
        for rel in REQUIRED_DATA
    }
    code_files = {rel: (root / rel).is_file() for rel in REQUIRED_CODE}
    gguf_files = sorted(
        str(path.relative_to(root)).replace("\\", "/")
        for path in (root / "models").glob("*.gguf")
        if path.is_file()
    )
    llama_candidates = [
        root / "bin" / "llama-server",
        root / "bin" / "llama-server.exe",
    ]
    llama_files = [
        str(path.relative_to(root)).replace("\\", "/")
        for path in llama_candidates
        if path.is_file()
    ]
    configs = []
    physical_meter_configured = True
    environment_meter_configured = True
    for rel in ("configs/radxa.experiment.json", "configs/radxa.challenge.json"):
        path = root / rel
        if not path.is_file():
            physical_meter_configured = False
            environment_meter_configured = False
            continue
        config = json.loads(path.read_text(encoding="utf-8"))
        telemetry = config.get("telemetry", {})
        power_paths = telemetry.get("power_paths", [])
        external = telemetry.get("external_meter", {})
        external_ready = bool(
            external.get("required_for_formal_run")
            and external.get("marker_host_env")
            and float(external.get("minimum_power_sample_rate_hz", 0)) >= 100
        )
        environment_ready = bool(
            "SHT31" in str(external.get("meter", ""))
            and float(external.get("environment_sample_interval_seconds", 0)) > 0
        )
        configs.append(
            {
                "path": rel,
                "power_paths": power_paths,
                "external_meter": external,
            }
        )
        if not power_paths and not external_ready:
            physical_meter_configured = False
        if not environment_ready:
            environment_meter_configured = False

    gates = {
        "formal_data_complete": all(item["exists"] for item in data_files.values()),
        "gold_test_final_evaluation_eligible": all(
            final_test_eligible(root / rel)
            for rel in (
                "data/splits_stratified_v2/test_op.jsonl",
                "data/splits_stratified_v2/test_ch.jsonl",
            )
        ),
        "radxa_scripts_and_configs_complete": all(code_files.values()),
        "gguf_model_present": bool(gguf_files),
        "llama_server_present": bool(llama_files),
        "physical_power_interface_configured": physical_meter_configured,
        "sht31_environment_interface_configured": environment_meter_configured,
        "actual_radxa_device_info_collected": (
            root / "results" / "radxa_device_info_formal_v1.0.json"
        ).is_file(),
    }
    result = {
        "report_version": "v2.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "windows_staging_root": str(root),
        "target_root": "/home/radxa/sci-exp",
        "data_files": data_files,
        "code_files": code_files,
        "gguf_files": gguf_files,
        "llama_server_files": llama_files,
        "configs": configs,
        "gates": gates,
        "radxa_execution_ready": all(gates.values()),
        "interpretation": (
            "Windows侧数据与脚本通过不等于Radxa实测完成；模型、运行时、"
            "Gold Test资格、模型、运行时、物理功率接口和设备信息必须在目标Radxa上核验。"
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"gates": gates, "radxa_execution_ready": result["radxa_execution_ready"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
