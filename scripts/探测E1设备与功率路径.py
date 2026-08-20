#!/usr/bin/env python3
"""在E1上采集设备、系统、温度、功率候选路径和本地运行时信息。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path("/home/radxa/sci-exp")


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip("\x00\n ")
    except OSError:
        return None


def read_number(path: Path) -> float | None:
    value = read_text(path)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def run(command: list[str]) -> dict[str, Any]:
    if shutil.which(command[0]) is None:
        return {"available": False, "command": command, "returncode": None, "stdout": None}
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return {
        "available": True,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def meminfo() -> dict[str, int]:
    result: dict[str, int] = {}
    text = read_text(Path("/proc/meminfo")) or ""
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        parts = raw.split()
        if not parts:
            continue
        try:
            result[f"{key}_bytes"] = int(parts[0]) * 1024
        except ValueError:
            continue
    return result


def anonymous_device_id() -> str | None:
    machine_id = read_text(Path("/etc/machine-id"))
    if not machine_id:
        return None
    return hashlib.sha256(f"RAG-sci:E1:{machine_id}".encode()).hexdigest()[:16]


def thermal_zones() -> list[dict[str, Any]]:
    zones = []
    for temp_path in sorted(Path("/sys/class/thermal").glob("thermal_zone*/temp")):
        raw = read_number(temp_path)
        zones.append(
            {
                "path": str(temp_path),
                "type": read_text(temp_path.parent / "type"),
                "raw_value": raw,
                "temperature_c": raw / 1000.0 if raw is not None and raw > 200 else raw,
            }
        )
    return zones


def power_candidates() -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    patterns = (
        "/sys/class/hwmon/hwmon*/power*_input",
        "/sys/class/power_supply/*/power_now",
        "/sys/class/power_supply/*/current_now",
        "/sys/class/power_supply/*/voltage_now",
    )
    unit_hint = {
        "power": "typically_microwatt_unverified",
        "current": "typically_microampere_unverified",
        "voltage": "typically_microvolt_unverified",
    }
    for pattern in patterns:
        for path in sorted(Path("/").glob(pattern.lstrip("/"))):
            field = path.name
            kind = next((key for key in unit_hint if field.startswith(key)), "unknown")
            candidates.append(
                {
                    "path": str(path),
                    "field": field,
                    "value": read_number(path),
                    "unit_hint_only": unit_hint.get(kind, "unknown"),
                    "rail_name": read_text(path.parent / "name")
                    or read_text(path.parent / "type"),
                    "formal_use_allowed": False,
                }
            )
    return candidates


def governors() -> list[dict[str, str | None]]:
    return [
        {"path": str(path), "value": read_text(path)}
        for path in sorted(
            Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_governor")
        )
    ]


def runtime_candidates() -> dict[str, Any]:
    paths = [PROJECT_ROOT / "bin" / "llama-server"]
    command_path = shutil.which("llama-server")
    if command_path:
        paths.append(Path(command_path))
    result = []
    for path in paths:
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        result.append(
            {
                "path": str(path),
                "executable": os.access(path, os.X_OK),
                "size_bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
    return {"candidates": result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "results" / "E1设备与功率路径探测_v1.0.json",
    )
    args = parser.parse_args()

    result = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "device_id": "E1",
        "anonymous_device_instance_id": anonymous_device_id(),
        "hostname": platform.node(),
        "hardware": {
            "device_tree_model": read_text(Path("/proc/device-tree/model")),
            "device_tree_compatible": read_text(Path("/proc/device-tree/compatible")),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "lscpu": run(["lscpu"]),
            "memory": meminfo(),
            "storage": run(["lsblk", "-b", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL"]),
            "root_filesystem": shutil.disk_usage("/")._asdict(),
        },
        "software": {
            "platform": platform.platform(),
            "kernel": platform.release(),
            "python": platform.python_version(),
            "os_release": read_text(Path("/etc/os-release")),
            "cmake": run(["cmake", "--version"]),
            "gcc": run(["gcc", "--version"]),
            "git": run(["git", "--version"]),
        },
        "resource_state": {
            "thermal_zones": thermal_zones(),
            "cpu_governors": governors(),
            "load_average": os.getloadavg(),
        },
        "power_probe": {
            "candidates": power_candidates(),
            "formal_interpretation": (
                "候选路径只有在单位、采样频率和供电轨覆盖范围经实测核验后，"
                "才能写入正式配置；没有板级输入功率路径时必须使用外置功率计。"
            ),
        },
        "llama_server": runtime_candidates(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
