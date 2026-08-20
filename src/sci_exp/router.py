from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Protocol

from .features import query_features
from .schemas import QueryRecord


@dataclass(frozen=True)
class RoutingDecision:
    configuration: str
    predicted_risks: dict[str, float]
    feasible_configurations: tuple[str, ...]
    reason: str
    predicted_heads: dict[str, dict[str, float]] | None = None
    predicted_energy_j: dict[str, float] | None = None
    effective_memory_budget_mb: float | None = None
    energy_budget_j: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "configuration": self.configuration,
            "predicted_risks": self.predicted_risks,
            "feasible_configurations": list(self.feasible_configurations),
            "reason": self.reason,
            "predicted_heads": self.predicted_heads or {},
            "predicted_energy_j": self.predicted_energy_j or {},
            "effective_memory_budget_mb": self.effective_memory_budget_mb,
            "energy_budget_j": self.energy_budget_j,
        }


class HeuristicRiskPredictor:
    """Transparent bootstrap predictor; replace with a trained model for the paper."""

    offsets = {"C0": 0.18, "C1": 0.02, "C2": -0.04}

    def predict(self, query: QueryRecord, configuration: str) -> float:
        features = query_features(query)
        base = (
            0.05
            + 0.02 * min(features["urgency_term_count"], 3.0)
            + 0.01 * min(features["hazard_term_count"], 3.0)
            + 0.12 * features["surface_insufficient_information"]
            + 0.01 * min(features["multi_intent_connector_count"], 2.0)
        )
        return min(1.0, max(0.0, base + self.offsets.get(configuration, 1.0)))


class RiskPredictor(Protocol):
    def predict(self, query: QueryRecord, configuration: str) -> float: ...


class EnergyPredictorProtocol(Protocol):
    def predict(
        self,
        query_features: Mapping[str, Any],
        configuration: str,
        state: Mapping[str, Any] | None = None,
    ) -> float: ...


class SafetyConstrainedRouter:
    def __init__(
        self,
        thresholds: Mapping[str, Any],
        predicted_energy_j: Mapping[str, float],
        predicted_latency_ms: Mapping[str, float],
        *,
        memory_budget_mb: float,
        latency_budget_ms: float,
        predicted_memory_mb: Mapping[str, float] | None = None,
        risk_predictor: RiskPredictor | None = None,
        energy_predictor: EnergyPredictorProtocol | None = None,
        energy_budget_j: float | None = None,
        memory_headroom_fraction: float = 0.9,
    ) -> None:
        if thresholds and all(isinstance(value, Mapping) for value in thresholds.values()):
            self.head_thresholds = {
                str(head): {
                    str(configuration): float(threshold)
                    for configuration, threshold in values.items()
                }
                for head, values in thresholds.items()
            }
            self.thresholds = self.head_thresholds.get("combined_risk", {})
        else:
            self.thresholds = {
                str(key): float(value) for key, value in thresholds.items()
            }
            self.head_thresholds = {"combined_risk": self.thresholds}
        self.predicted_energy_j = {
            key: float(value) for key, value in predicted_energy_j.items()
        }
        self.predicted_latency_ms = {
            key: float(value) for key, value in predicted_latency_ms.items()
        }
        self.predicted_memory_mb = {
            key: float(value)
            for key, value in (
                predicted_memory_mb
                or {"C0": 1024, "C1": 1536, "C2": 2048, "C3": 64}
            ).items()
        }
        self.memory_budget_mb = memory_budget_mb
        self.latency_budget_ms = latency_budget_ms
        self.risk_predictor = risk_predictor or HeuristicRiskPredictor()
        self.energy_predictor = energy_predictor
        self.energy_budget_j = energy_budget_j
        self.memory_headroom_fraction = min(max(memory_headroom_fraction, 0.1), 1.0)

    def select(
        self,
        query: QueryRecord,
        state: Mapping[str, Any] | None = None,
    ) -> RoutingDecision:
        configurations = ("C0", "C1", "C2")
        features = query_features(query)
        predicted_heads: dict[str, dict[str, float]] = {}
        for configuration in configurations:
            predictor = self.risk_predictor
            if hasattr(predictor, "predict_heads"):
                values = predictor.predict_heads(query, configuration)  # type: ignore[attr-defined]
                predicted_heads[configuration] = {
                    str(head): float(score) for head, score in values.items()
                }
                if (
                    "combined_risk" in self.head_thresholds
                    and "combined_risk" not in predicted_heads[configuration]
                ):
                    predicted_heads[configuration]["combined_risk"] = (
                        max(predicted_heads[configuration].values())
                        if predicted_heads[configuration]
                        else 1.0
                    )
            else:
                predicted_heads[configuration] = {
                    "combined_risk": predictor.predict(query, configuration)
                }
        risks = {
            configuration: max(values.values()) if values else 1.0
            for configuration, values in predicted_heads.items()
        }
        dynamic_energy = {
            configuration: (
                self.energy_predictor.predict(features, configuration, state)
                if self.energy_predictor is not None
                else self.predicted_energy_j.get(configuration, float("inf"))
            )
            for configuration in configurations
        }
        state_memory = None
        if state is not None and state.get("available_memory_mb_min") is not None:
            try:
                state_memory = float(state["available_memory_mb_min"])
            except (TypeError, ValueError):
                state_memory = None
        effective_memory_budget = self.memory_budget_mb
        if state_memory is not None and state_memory > 0:
            effective_memory_budget = min(
                effective_memory_budget,
                state_memory * self.memory_headroom_fraction,
            )
        feasible = []
        for configuration in configurations:
            if any(
                predicted_heads[configuration].get(head, 1.0)
                > thresholds_by_configuration.get(configuration, -1.0)
                for head, thresholds_by_configuration in self.head_thresholds.items()
            ):
                continue
            if self.predicted_latency_ms.get(configuration, float("inf")) > self.latency_budget_ms:
                continue
            if self.predicted_memory_mb.get(configuration, float("inf")) > effective_memory_budget:
                continue
            if (
                self.energy_budget_j is not None
                and dynamic_energy.get(configuration, float("inf"))
                > self.energy_budget_j
            ):
                continue
            feasible.append(configuration)
        if not feasible:
            return RoutingDecision(
                configuration="C3",
                predicted_risks=risks,
                feasible_configurations=(),
                reason="no_configuration_satisfies_calibrated_safety_and_resource_constraints",
                predicted_heads=predicted_heads,
                predicted_energy_j=dynamic_energy,
                effective_memory_budget_mb=effective_memory_budget,
                energy_budget_j=self.energy_budget_j,
            )
        selected = min(
            feasible,
            key=lambda configuration: (
                dynamic_energy.get(configuration, float("inf")),
                self.predicted_latency_ms.get(configuration, float("inf")),
                configuration,
            ),
        )
        return RoutingDecision(
            configuration=selected,
            predicted_risks=risks,
            feasible_configurations=tuple(feasible),
            reason="minimum_predicted_energy_among_feasible_configurations",
            predicted_heads=predicted_heads,
            predicted_energy_j=dynamic_energy,
            effective_memory_budget_mb=effective_memory_budget,
            energy_budget_j=self.energy_budget_j,
        )


class SoftWeightingRouter:
    """Non-constrained baseline minimizing a soft risk/energy score."""

    def __init__(self, base: SafetyConstrainedRouter, *, risk_weight: float = 0.8) -> None:
        self.base = base
        self.risk_weight = min(max(float(risk_weight), 0.0), 1.0)

    def select(
        self,
        query: QueryRecord,
        state: Mapping[str, Any] | None = None,
    ) -> RoutingDecision:
        configurations = ("C0", "C1", "C2")
        features = query_features(query)
        predicted_heads: dict[str, dict[str, float]] = {}
        for configuration in configurations:
            predictor = self.base.risk_predictor
            if hasattr(predictor, "predict_heads"):
                predicted_heads[configuration] = {
                    str(head): float(value)
                    for head, value in predictor.predict_heads(query, configuration).items()  # type: ignore[attr-defined]
                }
            else:
                predicted_heads[configuration] = {
                    "combined_risk": float(predictor.predict(query, configuration))
                }
        risks = {
            configuration: max(values.values()) if values else 1.0
            for configuration, values in predicted_heads.items()
        }
        energies = {
            configuration: (
                self.base.energy_predictor.predict(features, configuration, state)
                if self.base.energy_predictor is not None
                else self.base.predicted_energy_j.get(configuration, float("inf"))
            )
            for configuration in configurations
        }
        state_memory = None
        if state is not None and state.get("available_memory_mb_min") is not None:
            try:
                state_memory = float(state["available_memory_mb_min"])
            except (TypeError, ValueError):
                state_memory = None
        memory_budget = self.base.memory_budget_mb
        if state_memory is not None and state_memory > 0:
            memory_budget = min(
                memory_budget,
                state_memory * self.base.memory_headroom_fraction,
            )
        feasible = [
            configuration
            for configuration in configurations
            if self.base.predicted_latency_ms.get(configuration, float("inf"))
            <= self.base.latency_budget_ms
            and self.base.predicted_memory_mb.get(configuration, float("inf"))
            <= memory_budget
        ]
        if not feasible:
            return RoutingDecision(
                configuration="C3",
                predicted_risks=risks,
                feasible_configurations=(),
                reason="soft_weighting_no_resource_feasible_configuration",
                predicted_heads=predicted_heads,
                predicted_energy_j=energies,
                effective_memory_budget_mb=memory_budget,
            )
        finite_energies = [
            energies[item] for item in feasible if math.isfinite(energies[item])
        ]
        energy_scale = max(finite_energies) if finite_energies else 1.0
        selected = min(
            feasible,
            key=lambda configuration: (
                self.risk_weight * risks[configuration]
                + (1.0 - self.risk_weight)
                * energies[configuration]
                / max(energy_scale, 1.0e-9),
                configuration,
            ),
        )
        return RoutingDecision(
            configuration=selected,
            predicted_risks=risks,
            feasible_configurations=tuple(feasible),
            reason="soft_weighted_predicted_risk_and_energy_without_calibrated_safety_constraint",
            predicted_heads=predicted_heads,
            predicted_energy_j=energies,
            effective_memory_budget_mb=memory_budget,
        )
