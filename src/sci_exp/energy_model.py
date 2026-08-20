from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


QUERY_FEATURE_NAMES = (
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

STATE_FEATURE_NAMES = (
    "device_temperature_c_start",
    "available_memory_mb_min",
    "load_1m_peak",
    "cpu_frequency_mhz_start",
    "cpu_frequency_mhz_min",
    "cooling_state_peak",
)

CONFIGURATIONS = ("C0", "C1", "C2", "C3")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def row_energy(row: Mapping[str, Any]) -> float | None:
    telemetry = row.get("telemetry")
    if not isinstance(telemetry, Mapping):
        return None
    value = telemetry.get("energy_j")
    if value is None:
        return None
    energy = _number(value, float("nan"))
    if not math.isfinite(energy) or energy < 0:
        return None
    if telemetry.get("external_meter_valid") is False:
        return None
    return energy


def row_state(row: Mapping[str, Any]) -> dict[str, float]:
    telemetry = row.get("telemetry")
    source = telemetry if isinstance(telemetry, Mapping) else {}
    return {name: _number(source.get(name)) for name in STATE_FEATURE_NAMES}


def feature_vector(
    query_features: Mapping[str, Any],
    configuration: str,
    state: Mapping[str, Any] | None,
    *,
    include_state: bool,
) -> list[float]:
    values = [_number(query_features.get(name)) for name in QUERY_FEATURE_NAMES]
    values.extend(float(configuration == item) for item in CONFIGURATIONS)
    if include_state:
        state = state or {}
        values.extend(_number(state.get(name)) for name in STATE_FEATURE_NAMES)
    return values


def training_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    include_state: bool,
) -> tuple[list[list[float]], list[float]]:
    features: list[list[float]] = []
    targets: list[float] = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        energy = row_energy(row)
        raw_features = row.get("query_features")
        configuration = str(row.get("configuration", ""))
        if energy is None or not isinstance(raw_features, Mapping):
            continue
        if configuration not in CONFIGURATIONS:
            continue
        features.append(
            feature_vector(
                raw_features,
                configuration,
                row_state(row),
                include_state=include_state,
            )
        )
        targets.append(energy)
    if not features:
        raise ValueError("没有可用于能耗建模的有效物理能耗运行")
    return features, targets


def build_static_energy_table(
    rows: Iterable[Mapping[str, Any]],
) -> dict[str, float]:
    grouped: dict[str, list[float]] = {key: [] for key in CONFIGURATIONS}
    for row in rows:
        configuration = str(row.get("configuration", ""))
        energy = row_energy(row)
        if configuration in grouped and energy is not None:
            grouped[configuration].append(energy)
    return {
        configuration: statistics.mean(values)
        for configuration, values in grouped.items()
        if values
    }


@dataclass
class EnergyPredictor:
    mode: str
    static_table: dict[str, float]
    estimator: Any = None

    def predict(
        self,
        query_features: Mapping[str, Any],
        configuration: str,
        state: Mapping[str, Any] | None = None,
    ) -> float:
        if self.mode == "static_mean":
            return float(self.static_table.get(configuration, float("inf")))
        if self.estimator is None:
            return float("inf")
        vector = feature_vector(
            query_features,
            configuration,
            state,
            include_state=self.mode == "state_aware",
        )
        prediction = float(self.estimator.predict([vector])[0])
        return max(0.0, prediction)


def fit_energy_predictors(
    rows: Iterable[Mapping[str, Any]],
    *,
    random_state: int = 42,
) -> dict[str, EnergyPredictor]:
    cached = list(rows)
    static_table = build_static_energy_table(cached)
    if not static_table:
        raise ValueError("静态能耗表没有有效配置")
    try:
        from sklearn.ensemble import RandomForestRegressor
    except ImportError as exc:  # pragma: no cover - dependency gate
        raise RuntimeError("E3需要scikit-learn；安装research依赖") from exc

    result = {
        "static_mean": EnergyPredictor("static_mean", static_table),
    }
    for mode, include_state in (("no_state", False), ("state_aware", True)):
        x, y = training_rows(cached, include_state=include_state)
        estimator = RandomForestRegressor(
            n_estimators=300,
            min_samples_leaf=max(1, min(3, len(y) // 20)),
            random_state=random_state,
            n_jobs=1,
        )
        estimator.fit(x, y)
        result[mode] = EnergyPredictor(mode, dict(static_table), estimator)
    return result


def save_energy_predictors(
    predictors: Mapping[str, EnergyPredictor],
    directory: str | Path,
) -> dict[str, str]:
    try:
        import joblib
    except ImportError as exc:  # pragma: no cover - dependency gate
        raise RuntimeError("保存能耗模型需要joblib") from exc
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for name, predictor in predictors.items():
        path = target / f"energy_{name}.joblib"
        joblib.dump(predictor, path)
        paths[name] = str(path)
    return paths


def load_energy_predictor(path: str | Path) -> EnergyPredictor:
    try:
        import joblib
    except ImportError as exc:  # pragma: no cover - dependency gate
        raise RuntimeError("加载能耗模型需要joblib") from exc
    value = joblib.load(path)
    if not isinstance(value, EnergyPredictor):
        raise ValueError(f"不是sci-exp能耗模型: {path}")
    return value
