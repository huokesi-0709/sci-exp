from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sci_exp.energy_model import (  # noqa: E402
    fit_energy_predictors,
    row_energy,
    row_state,
    save_energy_predictors,
)


def read_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def safe(row: dict[str, Any]) -> bool:
    label = row.get("adjudication")
    if not isinstance(label, dict):
        return True
    if all(name in label for name in ("y_trigger", "y_miss", "y_quality")):
        return not bool(label["y_trigger"]) and not bool(label["y_miss"]) and bool(label["y_quality"])
    return not bool(label.get("severe_failure", True))


def prediction_rows(rows: list[dict[str, Any]], predictor: Any) -> list[dict[str, Any]]:
    values = []
    for row in rows:
        actual = row_energy(row)
        features = row.get("query_features")
        configuration = str(row.get("configuration", ""))
        if row.get("status") != "ok" or actual is None or not isinstance(features, dict):
            continue
        predicted = predictor.predict(features, configuration, row_state(row))
        values.append(
            {
                "query_id": str(row.get("query_id", "")),
                "source_group_id": str(row.get("source_group_id", "")),
                "repetition": int(row.get("repetition", 0)),
                "configuration": configuration,
                "actual_energy_j": actual,
                "predicted_energy_j": predicted,
                "safe": safe(row),
            }
        )
    return values


def regression_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    errors = [abs(row["predicted_energy_j"] - row["actual_energy_j"]) for row in rows]
    percentage = [
        abs(row["predicted_energy_j"] - row["actual_energy_j"]) / row["actual_energy_j"]
        for row in rows
        if row["actual_energy_j"] >= 0.1
    ]
    squared = [(row["predicted_energy_j"] - row["actual_energy_j"]) ** 2 for row in rows]
    return {
        "n": len(rows),
        "mae_j": statistics.mean(errors) if errors else None,
        "median_absolute_error_j": statistics.median(errors) if errors else None,
        "rmse_j": math.sqrt(statistics.mean(squared)) if squared else None,
        "mape_energy_ge_0_1j": statistics.mean(percentage) if percentage else None,
    }


def routing_metrics(rows: list[dict[str, Any]], budgets: list[float]) -> dict[str, Any]:
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["query_id"], row["repetition"])].append(row)
    regrets = []
    correlations = []
    selected_actual = []
    complete = 0
    try:
        from scipy.stats import spearmanr
    except ImportError:
        spearmanr = None
    for group in groups.values():
        safe_group = [row for row in group if row["safe"]]
        if len(safe_group) < 2:
            continue
        complete += 1
        selected = min(safe_group, key=lambda row: (row["predicted_energy_j"], row["configuration"]))
        oracle = min(safe_group, key=lambda row: (row["actual_energy_j"], row["configuration"]))
        regrets.append(selected["actual_energy_j"] - oracle["actual_energy_j"])
        selected_actual.append(selected["actual_energy_j"])
        if spearmanr is not None and len(safe_group) >= 2:
            result = spearmanr(
                [row["predicted_energy_j"] for row in safe_group],
                [row["actual_energy_j"] for row in safe_group],
            )
            if math.isfinite(float(result.statistic)):
                correlations.append(float(result.statistic))
    return {
        "complete_safe_query_repetitions": complete,
        "mean_energy_regret_j": statistics.mean(regrets) if regrets else None,
        "median_energy_regret_j": statistics.median(regrets) if regrets else None,
        "mean_within_query_spearman": statistics.mean(correlations) if correlations else None,
        "budget_violation_rate": {
            str(budget): sum(value > budget for value in selected_actual) / len(selected_actual)
            if selected_actual else None
            for budget in budgets
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="E3静态/无状态/硬件状态感知能耗预测比较")
    parser.add_argument("--train", required=True, type=Path)
    parser.add_argument("--test", required=True, type=Path)
    parser.add_argument("--model-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--budgets-j", default="10,5,3")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    train = read_rows(args.train)
    test = read_rows(args.test)
    train_groups = {str(row.get("source_group_id", "")) for row in train if row.get("source_group_id")}
    test_groups = {str(row.get("source_group_id", "")) for row in test if row.get("source_group_id")}
    overlap = sorted(train_groups & test_groups)
    if overlap:
        raise SystemExit(f"训练/测试source_group_id泄漏: {overlap[:10]}")
    predictors = fit_energy_predictors(train, random_state=args.seed)
    paths = save_energy_predictors(predictors, args.model_directory)
    budgets = [float(value) for value in args.budgets_j.split(",") if value.strip()]
    report: dict[str, Any] = {
        "schema_version": "e3-energy-prediction-v1.0",
        "train": str(args.train),
        "test": str(args.test),
        "source_group_overlap": overlap,
        "models": {},
    }
    for name, predictor in predictors.items():
        predicted = prediction_rows(test, predictor)
        report["models"][name] = {
            "artifact": paths[name],
            "regression": regression_metrics(predicted),
            "routing": routing_metrics(predicted, budgets),
        }
    state = report["models"]["state_aware"]["routing"]
    static = report["models"]["static_mean"]["routing"]
    no_state = report["models"]["no_state"]["routing"]
    report["contribution_gate"] = {
        "state_aware_regret_below_static": (
            state["mean_energy_regret_j"] is not None
            and static["mean_energy_regret_j"] is not None
            and state["mean_energy_regret_j"] < static["mean_energy_regret_j"]
        ),
        "state_aware_regret_below_no_state": (
            state["mean_energy_regret_j"] is not None
            and no_state["mean_energy_regret_j"] is not None
            and state["mean_energy_regret_j"] < no_state["mean_energy_regret_j"]
        ),
        "interpretation": "两项均不成立时，hardware-aware只能作为负结果或鲁棒性分析，不能作为核心贡献。",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": list(report["models"]), "gate": report["contribution_gate"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
