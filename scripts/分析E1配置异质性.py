from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


CONFIG_ORDER = {"C0": 0, "C1": 1, "C2": 2, "C3": 3}


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def safe(row: dict[str, Any]) -> bool:
    label = row.get("adjudication")
    if not isinstance(label, dict):
        return False
    if all(name in label for name in ("y_trigger", "y_miss", "y_quality")):
        return not bool(label["y_trigger"]) and not bool(label["y_miss"]) and bool(label["y_quality"])
    return not bool(label.get("severe_failure", True))


def energy(row: dict[str, Any]) -> float | None:
    telemetry = row.get("telemetry") or {}
    value = telemetry.get("energy_j")
    if value is None or telemetry.get("external_meter_valid") is False:
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description="E1配置异质性与最低能耗安全Oracle")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--oracle-output", required=True, type=Path)
    args = parser.parse_args()

    rows = read_rows(args.input)
    candidates = [
        row
        for row in rows
        if row.get("status") == "ok"
        and str(row.get("configuration")) in {"C0", "C1", "C2"}
        and energy(row) is not None
        and isinstance(row.get("adjudication"), dict)
    ]
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        groups[(str(row["query_id"]), int(row.get("repetition", 0)))].append(row)

    oracle_rows: list[dict[str, Any]] = []
    safety_matrix: Counter[str] = Counter()
    for (query_id, repetition), group in sorted(groups.items()):
        by_configuration = {str(row["configuration"]): row for row in group}
        if set(by_configuration) != {"C0", "C1", "C2"}:
            continue
        safe_configurations = sorted(
            (configuration for configuration, row in by_configuration.items() if safe(row)),
            key=lambda item: CONFIG_ORDER[item],
        )
        matrix_key = "|".join(safe_configurations) if safe_configurations else "NONE"
        safety_matrix[matrix_key] += 1
        if safe_configurations:
            selected = min(
                safe_configurations,
                key=lambda configuration: (energy(by_configuration[configuration]), CONFIG_ORDER[configuration]),
            )
            selected_row = by_configuration[selected]
            oracle_energy = energy(selected_row)
        else:
            selected = "C3"
            oracle_energy = None
        oracle_rows.append(
            {
                "schema_version": "e1-safe-oracle-v1.0",
                "query_id": query_id,
                "source_group_id": group[0].get("source_group_id", ""),
                "split": group[0].get("split", ""),
                "repetition": repetition,
                "safe_configurations": safe_configurations,
                "oracle_configuration": selected,
                "oracle_energy_j": oracle_energy,
                "configuration_energy_j": {
                    configuration: energy(row)
                    for configuration, row in sorted(by_configuration.items())
                },
                "configuration_safe": {
                    configuration: safe(row)
                    for configuration, row in sorted(by_configuration.items())
                },
            }
        )

    distribution = Counter(str(row["oracle_configuration"]) for row in oracle_rows)
    total = len(oracle_rows)
    entropy = -sum(
        (count / total) * math.log(count / total, 2)
        for count in distribution.values()
        if count and total
    ) if total else 0.0
    configuration_summary = {}
    for configuration in ("C0", "C1", "C2"):
        subset = [row for row in candidates if row["configuration"] == configuration]
        energies = [energy(row) for row in subset]
        valid_energies = [float(value) for value in energies if value is not None]
        configuration_summary[configuration] = {
            "n": len(subset),
            "safe_rate": sum(safe(row) for row in subset) / len(subset) if subset else None,
            "energy_j_mean": statistics.mean(valid_energies) if valid_energies else None,
            "energy_j_median": statistics.median(valid_energies) if valid_energies else None,
        }
    report = {
        "schema_version": "e1-configuration-heterogeneity-v1.0",
        "complete_query_repetitions": total,
        "oracle_configuration_distribution": dict(sorted(distribution.items())),
        "oracle_configuration_entropy_bits": entropy,
        "oracle_uses_multiple_configurations": len([key for key, value in distribution.items() if value]) > 1,
        "safety_set_matrix": dict(sorted(safety_matrix.items())),
        "configuration_summary": configuration_summary,
        "router_necessity_gate": bool(total and len(distribution) > 1 and entropy > 0),
        "interpretation": "若Oracle几乎恒定选择同一配置，异质路由的必要性不成立。",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_rows(args.oracle_output, oracle_rows)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if total else 2


if __name__ == "__main__":
    raise SystemExit(main())
