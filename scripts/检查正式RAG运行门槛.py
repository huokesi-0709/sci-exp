from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查正式RAG、BGE和Radxa运行门槛")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/logs/正式RAG运行门槛检查_v1.0.json"),
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    manifest_path = root / "configs" / "正式配置清单_v1.0.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    knowledge = root / manifest["knowledge_base"]["path"]
    dense = root / manifest["dense_encoder"]["path_windows"] / "model.safetensors"
    gguf = root / manifest["common_generation"]["gguf_file"]
    llama_candidates = [
        root / "bin" / "llama-server",
        root / "bin" / "llama-server.exe",
    ]
    device_logs = list((root / "data" / "logs").glob("E1_设备信息*.json"))
    power_logs = list((root / "data" / "logs").glob("E1_功率路径*.json"))
    firmware = (
        root
        / "hardware"
        / "esp32s3_ina226_power_meter"
        / "src"
        / "main.cpp"
    )
    firmware_build_logs = list(
        (root / "data" / "logs").glob("ESP32S3_INA226固件构建*.json")
    )
    calibration_logs = list(
        (root / "data" / "logs").glob("INA226三点校准*.json")
    )
    checks = {
        "manifest_exists": manifest_path.is_file(),
        "knowledge_base_exists": knowledge.is_file(),
        "knowledge_base_hash_matches": knowledge.is_file()
        and sha256(knowledge) == manifest["knowledge_base"]["sha256"],
        "dense_weight_exists": dense.is_file(),
        "dense_weight_hash_matches": dense.is_file()
        and sha256(dense) == manifest["dense_encoder"]["formal_weight_sha256"],
        "gguf_exists": gguf.is_file(),
        "sentence_transformers_runtime_available": (
            importlib.util.find_spec("sentence_transformers") is not None
            and importlib.util.find_spec("torch") is not None
        ),
        "arm64_llama_server_present": any(path.is_file() for path in llama_candidates),
        "e1_device_probe_present": bool(device_logs),
        "e1_power_probe_present": bool(power_logs),
        "esp32_ina226_firmware_source_present": firmware.is_file(),
        "platformio_available": shutil.which("pio") is not None,
        "esp32_firmware_build_evidence_present": bool(firmware_build_logs),
        "ina226_three_point_calibration_present": bool(calibration_logs),
    }
    code_and_asset_gate = all(
        checks[key]
        for key in (
            "manifest_exists",
            "knowledge_base_exists",
            "knowledge_base_hash_matches",
            "dense_weight_exists",
            "dense_weight_hash_matches",
            "gguf_exists",
        )
    )
    runtime_gate = all(checks.values())
    report = {
        "schema_version": "formal-rag-runtime-gate-v1.0",
        "root": str(root),
        "checks": checks,
        "code_and_asset_gate": code_and_asset_gate,
        "formal_runtime_gate": runtime_gate,
        "allowed_now": [
            "Windows hashing/extractive development diagnostics",
            "schema and unit tests",
        ],
        "blocked_until_runtime_gate": [
            "formal C0-C3 output generation",
            "output-level double review",
            "AI+ predictor training on potential outcomes",
            "Radxa resource and physical-energy claims",
        ],
        "blockers": [key for key, passed in checks.items() if not passed],
    }
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if runtime_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
