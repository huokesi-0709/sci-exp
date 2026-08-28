from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable

from .features import query_features
from .schemas import InferenceQuery


DEFAULT_FEATURES = (
    "token_count",
    "character_count",
    "has_question_mark",
    "urgency_term_count",
    "hazard_term_count",
    "context_term_count",
    "negation_count",
    "multi_intent_connector_count",
    "has_numeric_detail",
    "surface_insufficient_information",
)


def train_logistic_risk_models(
    rows: Iterable[dict[str, Any]],
    *,
    feature_names: tuple[str, ...] = DEFAULT_FEATURES,
    iterations: int = 1200,
    learning_rate: float = 0.1,
    l2: float = 0.01,
) -> dict[str, Any]:
    grouped: dict[
        str, dict[str, list[tuple[list[float], float]]]
    ] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row.get("status") != "ok":
            continue
        configuration = str(row["configuration"])
        raw_features = row.get("query_features")
        metrics = row.get("adjudication", row.get("metrics"))
        if not isinstance(raw_features, dict) or not isinstance(metrics, dict):
            continue
        vector = [float(raw_features[name]) for name in feature_names]
        for head, label in _label_values(metrics).items():
            grouped[head][configuration].append((vector, float(label)))
    if not grouped:
        raise ValueError("no successful labeled experiment rows with query_features")
    heads = {
        head: {
            configuration: _fit_one(
                samples,
                iterations=iterations,
                learning_rate=learning_rate,
                l2=l2,
            )
            for configuration, samples in sorted(configurations.items())
        }
        for head, configurations in sorted(grouped.items())
    }
    primary_head = (
        "combined_risk"
        if "combined_risk" in heads
        else "severe_failure"
        if "severe_failure" in heads
        else sorted(heads)[0]
    )
    return {
        "schema_version": "2.0",
        "model_type": "multi_head_per_configuration_logistic_regression",
        "feature_names": list(feature_names),
        "heads": heads,
        "primary_head": primary_head,
        # Compatibility for v1 callers that expect one models mapping.
        "models": heads[primary_head],
        "warning": "Train only on train/validation groups; never train on calibration or test groups.",
    }


def _label_values(metrics: dict[str, Any]) -> dict[str, bool]:
    values: dict[str, bool] = {}
    new_labels_present = all(
        name in metrics for name in ("y_trigger", "y_miss", "y_quality")
    )
    if new_labels_present:
        values.update(
            {
                "trigger": bool(metrics["y_trigger"]),
                "miss": bool(metrics["y_miss"]),
                "quality_failure": not bool(metrics["y_quality"]),
                "combined_risk": bool(metrics["y_trigger"])
                or bool(metrics["y_miss"])
                or not bool(metrics["y_quality"]),
            }
        )
    if "severe_failure" in metrics:
        values["severe_failure"] = bool(metrics["severe_failure"])
    return values


def _fit_one(
    samples: list[tuple[list[float], float]],
    *,
    iterations: int,
    learning_rate: float,
    l2: float,
) -> dict[str, Any]:
    dimension = len(samples[0][0])
    means = [
        sum(vector[index] for vector, _ in samples) / len(samples)
        for index in range(dimension)
    ]
    scales = []
    for index in range(dimension):
        variance = (
            sum((vector[index] - means[index]) ** 2 for vector, _ in samples)
            / len(samples)
        )
        scales.append(max(math.sqrt(variance), 1.0e-8))
    standardized = [
        (
            [
                (vector[index] - means[index]) / scales[index]
                for index in range(dimension)
            ],
            label,
        )
        for vector, label in samples
    ]
    prevalence = (sum(label for _, label in samples) + 0.5) / (len(samples) + 1.0)
    intercept = math.log(prevalence / (1.0 - prevalence))
    coefficients = [0.0] * dimension
    if len({label for _, label in samples}) > 1:
        for iteration in range(iterations):
            intercept_gradient = 0.0
            coefficient_gradients = [0.0] * dimension
            for vector, label in standardized:
                probability = _sigmoid(
                    intercept
                    + sum(weight * value for weight, value in zip(coefficients, vector))
                )
                error = probability - label
                intercept_gradient += error
                for index, value in enumerate(vector):
                    coefficient_gradients[index] += error * value
            step = learning_rate / math.sqrt(1.0 + iteration / 50.0)
            intercept -= step * intercept_gradient / len(samples)
            for index in range(dimension):
                gradient = coefficient_gradients[index] / len(samples) + l2 * coefficients[index]
                coefficients[index] -= step * gradient
    return {
        "n_samples": len(samples),
        "failure_rate": sum(label for _, label in samples) / len(samples),
        "intercept": intercept,
        "coefficients": coefficients,
        "means": means,
        "scales": scales,
    }


class LogisticRiskPredictor:
    def __init__(self, model: dict[str, Any]) -> None:
        self.feature_names = tuple(str(name) for name in model["feature_names"])
        self.primary_head = str(model.get("primary_head", "severe_failure"))
        self.heads = model.get("heads") or {
            self.primary_head: model["models"]
        }
        self.models = self.heads.get(self.primary_head, model["models"])

    def predict(self, query: InferenceQuery, configuration: str) -> float:
        features = query_features(query)
        return self.predict_features(features, configuration)

    def predict_features(
        self,
        features: dict[str, float],
        configuration: str,
    ) -> float:
        if configuration not in self.models:
            return 1.0
        model = self.models[configuration]
        vector = [
            (float(features[name]) - float(mean)) / max(float(scale), 1.0e-8)
            for name, mean, scale in zip(
                self.feature_names,
                model["means"],
                model["scales"],
            )
        ]
        logit = float(model["intercept"]) + sum(
            float(weight) * value
            for weight, value in zip(model["coefficients"], vector)
        )
        return _sigmoid(logit)

    def predict_heads(
        self,
        query: InferenceQuery,
        configuration: str,
    ) -> dict[str, float]:
        return self.predict_feature_heads(query_features(query), configuration)

    def predict_feature_heads(
        self,
        features: dict[str, float],
        configuration: str,
    ) -> dict[str, float]:
        original_models = self.models
        result: dict[str, float] = {}
        try:
            for head, models in self.heads.items():
                self.models = models
                result[str(head)] = self.predict_features(features, configuration)
        finally:
            self.models = original_models
        return result


def score_experiment_rows(
    rows: Iterable[dict[str, Any]],
    predictor: LogisticRiskPredictor,
) -> list[dict[str, Any]]:
    scored = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        features = row.get("query_features")
        metrics = row.get("adjudication", row.get("metrics"))
        if not isinstance(features, dict) or not isinstance(metrics, dict):
            continue
        risk_scores = predictor.predict_feature_heads(
            features, str(row["configuration"])
        )
        labels = _label_values(metrics)
        scored.append(
            {
                "query_id": row["query_id"],
                "source_group_id": row.get("source_group_id", ""),
                "split": row.get("split", ""),
                "configuration": row["configuration"],
                "risk_score": max(risk_scores.values()) if risk_scores else 1.0,
                "risk_scores": risk_scores,
                "failure": bool(
                    labels.get("combined_risk", labels.get("severe_failure", True))
                ),
                "labels": labels,
            }
        )
    return scored


def _sigmoid(value: float) -> float:
    if value >= 0:
        factor = math.exp(-value)
        return 1.0 / (1.0 + factor)
    factor = math.exp(value)
    return factor / (1.0 + factor)
