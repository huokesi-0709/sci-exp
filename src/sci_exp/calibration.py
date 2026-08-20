from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CalibrationResult:
    threshold: float
    accepted: int
    failures: int
    empirical_risk: float
    upper_risk: float
    coverage: float
    bound_method: str

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "threshold": self.threshold,
            "accepted": self.accepted,
            "failures": self.failures,
            "empirical_risk": self.empirical_risk,
            "upper_risk": self.upper_risk,
            "coverage": self.coverage,
            "bound_method": self.bound_method,
        }


def binomial_upper_bound(failures: int, count: int, delta: float) -> tuple[float, str]:
    if not 0 < delta < 1:
        raise ValueError("delta must be between 0 and 1")
    if count <= 0 or failures < 0 or failures > count:
        raise ValueError("require 0 <= failures <= count and count > 0")
    try:
        from scipy.stats import beta  # type: ignore

        if failures == count:
            return 1.0, "clopper-pearson"
        value = float(beta.ppf(1.0 - delta, failures + 1, count - failures))
        return value, "clopper-pearson"
    except ImportError:
        # One-sided Wilson bound is a dependency-free conservative fallback.
        z = _inverse_standard_normal(1.0 - delta)
        probability = failures / count
        denominator = 1.0 + z * z / count
        center = probability + z * z / (2.0 * count)
        spread = z * math.sqrt(
            probability * (1.0 - probability) / count
            + z * z / (4.0 * count * count)
        )
        return min(1.0, (center + spread) / denominator), "wilson"


def select_threshold(
    labeled_scores: Iterable[tuple[float, bool]],
    *,
    alpha: float,
    delta: float,
) -> CalibrationResult:
    if not 0 <= alpha <= 1:
        raise ValueError("alpha must be between 0 and 1")
    rows = sorted((float(score), bool(failure)) for score, failure in labeled_scores)
    if not rows:
        raise ValueError("calibration data is empty")
    best: CalibrationResult | None = None
    for threshold in sorted({score for score, _ in rows}):
        accepted_rows = [failure for score, failure in rows if score <= threshold]
        failures = sum(accepted_rows)
        upper, method = binomial_upper_bound(failures, len(accepted_rows), delta)
        result = CalibrationResult(
            threshold=threshold,
            accepted=len(accepted_rows),
            failures=failures,
            empirical_risk=failures / len(accepted_rows),
            upper_risk=upper,
            coverage=len(accepted_rows) / len(rows),
            bound_method=method,
        )
        if upper <= alpha and (
            best is None
            or result.coverage > best.coverage
            or (
                result.coverage == best.coverage
                and result.threshold > best.threshold
            )
        ):
            best = result
    if best is not None:
        return best
    return CalibrationResult(
        threshold=-1.0,
        accepted=0,
        failures=0,
        empirical_risk=0.0,
        upper_risk=1.0,
        coverage=0.0,
        bound_method="no-feasible-threshold",
    )


def _inverse_standard_normal(probability: float) -> float:
    """Acklam's approximation, sufficient for a statistical fallback."""
    if not 0 < probability < 1:
        raise ValueError("probability must be between 0 and 1")
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    lower = 0.02425
    upper = 1.0 - lower
    if probability < lower:
        q = math.sqrt(-2.0 * math.log(probability))
        return _polynomial(c, q) / _polynomial((*d, 1.0), q)
    if probability <= upper:
        q = probability - 0.5
        r = q * q
        return _polynomial(a, r) * q / _polynomial((*b, 1.0), r)
    q = math.sqrt(-2.0 * math.log(1.0 - probability))
    return -_polynomial(c, q) / _polynomial((*d, 1.0), q)


def _polynomial(coefficients: tuple[float, ...], value: float) -> float:
    result = 0.0
    for coefficient in coefficients:
        result = result * value + coefficient
    return result
