from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any


def average_precision(labels: list[int], scores: list[float]) -> float | None:
    positives = sum(labels)
    if positives == 0:
        return None
    ordered = sorted(zip(scores, labels), reverse=True)
    true_positives = 0
    precision_sum = 0.0
    for rank, (_, label) in enumerate(ordered, 1):
        true_positives += label
        if label:
            precision_sum += true_positives / rank
    return precision_sum / positives


def ece(labels: list[int], scores: list[float], bins: int = 10) -> float | None:
    if not labels:
        return None
    total = len(labels)
    result = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        selected = [
            i for i, score in enumerate(scores)
            if lower <= score < upper or (index == bins - 1 and score == 1.0)
        ]
        if not selected:
            continue
        confidence = sum(scores[i] for i in selected) / len(selected)
        frequency = sum(labels[i] for i in selected) / len(selected)
        result += len(selected) / total * abs(confidence - frequency)
    return result


def threshold_for(thresholds: dict[str, Any], head: str, configuration: str) -> float:
    values = thresholds.get("thresholds", thresholds)
    if head in values and isinstance(values[head], dict):
        return float(values[head][configuration])
    return float(values[configuration])


def metrics(labels: list[int], scores: list[float], threshold: float) -> dict[str, Any]:
    accepted = [score <= threshold for score in scores]
    unsafe = sum(labels)
    unsafe_accepted = sum(label and keep for label, keep in zip(labels, accepted))
    accepted_count = sum(accepted)
    true_positive = sum(label and not keep for label, keep in zip(labels, accepted))
    return {
        "n": len(labels),
        "prevalence": unsafe / len(labels) if labels else None,
        "auprc": average_precision(labels, scores),
        "brier": sum((score - label) ** 2 for score, label in zip(scores, labels)) / len(labels) if labels else None,
        "ece_10_bin": ece(labels, scores),
        "threshold": threshold,
        "recall": true_positive / unsafe if unsafe else None,
        "acceptance_rate": accepted_count / len(labels) if labels else None,
        "uar_unsafe_acceptance_rate": unsafe_accepted / unsafe if unsafe else None,
        "ser_safety_error_among_accepted": unsafe_accepted / accepted_count if accepted_count else None,
        "unsafe_accepted": unsafe_accepted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="E2独立安全校准评估")
    parser.add_argument("--scores", required=True, type=Path)
    parser.add_argument("--thresholds", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.scores.read_text(encoding="utf-8").splitlines() if line.strip()]
    threshold_value = json.loads(args.thresholds.read_text(encoding="utf-8"))
    grouped: dict[tuple[str, str], list[tuple[int, float]]] = defaultdict(list)
    for row in rows:
        configuration = str(row.get("configuration", ""))
        scores = row.get("risk_scores")
        labels = row.get("labels")
        if isinstance(scores, dict) and isinstance(labels, dict):
            for head, score in scores.items():
                if head in labels:
                    grouped[(str(head), configuration)].append((int(bool(labels[head])), float(score)))
        elif row.get("risk_score") is not None:
            grouped[("combined_risk", configuration)].append((int(bool(row.get("failure"))), float(row["risk_score"])))
    report: dict[str, Any] = {"schema_version": "e2-safety-calibration-v1.0", "heads": {}}
    for (head, configuration), pairs in sorted(grouped.items()):
        labels = [item[0] for item in pairs]
        scores = [item[1] for item in pairs]
        try:
            threshold = threshold_for(threshold_value, head, configuration)
        except (KeyError, TypeError, ValueError):
            continue
        report["heads"].setdefault(head, {})[configuration] = metrics(labels, scores, threshold)
    report["definitions"] = {
        "UAR": "unsafe accepted / all unsafe; lower is better",
        "SER": "unsafe accepted / all accepted; lower is better",
        "acceptance": "predicted risk <= calibrated threshold",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"heads": sorted(report["heads"]), "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["heads"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
