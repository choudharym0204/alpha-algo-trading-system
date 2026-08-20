"""Alpha and Beta against an aligned benchmark series (P16).

Alpha and Beta are only computed when a benchmark return series exists and
is **explicitly aligned** with the strategy return series (same length, same
frequency, same timestamp alignment). The package never aligns or pads
mismatched series silently — that would fabricate a benchmark relationship.

Method (fixed and auditable, population formulas consistent with the
engine's population-std Sharpe):

- ``beta = covariance(portfolio, benchmark) / variance(benchmark)``
  (population denominators).
- ``alpha = mean(portfolio) - risk_free - beta * (mean(benchmark) - risk_free)``
  (CAPM-style Jensen's alpha with an injected per-period risk-free rate).
- Undefined when there are fewer than two observations or when the benchmark
  variance is zero (``beta`` and ``alpha`` are then ``None``).

The caller must supply a ``benchmark_identity`` and ``frequency`` string so
the result is self-describing and can never be mistaken for a comparison
against an arbitrary, unlabeled series.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from alpha_algo_backtest_analytics.errors import RiskMeasureError

__all__ = ["ALPHA_BETA_POLICY", "AlphaBetaMetrics", "DECIMAL_PRECISION", "compute_alpha_beta"]

DECIMAL_PRECISION = 28

ALPHA_BETA_POLICY = (
    "Beta = population covariance(portfolio, benchmark) / population "
    "variance(benchmark); Alpha = mean(portfolio) - risk_free - beta * "
    "(mean(benchmark) - risk_free). Series must be explicitly aligned (equal "
    "length, equal frequency, same timestamp alignment) and labeled with a "
    "benchmark identity. Undefined (None) below two observations or when "
    "benchmark variance is zero."
)


@dataclass(frozen=True)
class AlphaBetaMetrics:
    """CAPM-style Alpha and Beta against a labeled benchmark series.

    These are informational reconstructions of the explicit historical
    inputs under the documented method; they imply no statistical guarantee
    and no forward performance.
    """

    benchmark_identity: str
    frequency: str
    observation_count: int
    alpha: Decimal | None
    beta: Decimal | None

    def __post_init__(self) -> None:
        for name, value in (("benchmark_identity", self.benchmark_identity), ("frequency", self.frequency)):
            if not isinstance(value, str) or not value:
                raise RiskMeasureError(f"{name} must be a non-empty string")
        if type(self.observation_count) is not int or self.observation_count < 0:
            raise RiskMeasureError("observation_count must be a non-negative int")
        for name, value in (("alpha", self.alpha), ("beta", self.beta)):
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
                raise RiskMeasureError(f"{name} must be a finite Decimal or None")
        if (self.alpha is None) != (self.beta is None):
            raise RiskMeasureError("alpha and beta must be None together (both defined or both undefined)")


def _validate_aligned(portfolio: tuple[Decimal, ...], benchmark: tuple[Decimal, ...]) -> None:
    if not isinstance(portfolio, tuple) or not isinstance(benchmark, tuple):
        raise RiskMeasureError("portfolio and benchmark must be tuples of Decimal")
    if len(portfolio) != len(benchmark):
        raise RiskMeasureError(
            f"portfolio and benchmark must be aligned (got {len(portfolio)} vs {len(benchmark)})"
        )
    for series, name in ((portfolio, "portfolio"), (benchmark, "benchmark")):
        for value in series:
            if not isinstance(value, Decimal) or not value.is_finite():
                raise RiskMeasureError(f"{name} must contain only finite Decimals")


def compute_alpha_beta(
    portfolio: tuple[Decimal, ...],
    benchmark: tuple[Decimal, ...],
    *,
    risk_free_rate_per_period: Decimal,
    benchmark_identity: str,
    frequency: str,
) -> AlphaBetaMetrics:
    """Compute CAPM-style Alpha and Beta over aligned return series.

    Returns ``alpha``/``beta`` as ``None`` when there are fewer than two
    observations or the benchmark variance is zero. Raises
    :class:`RiskMeasureError` on misalignment or malformed inputs.
    """
    _validate_aligned(portfolio, benchmark)
    if (
        not isinstance(risk_free_rate_per_period, Decimal)
        or not risk_free_rate_per_period.is_finite()
        or risk_free_rate_per_period < 0
    ):
        raise RiskMeasureError("risk_free_rate_per_period must be a non-negative finite Decimal")
    for name, value in (("benchmark_identity", benchmark_identity), ("frequency", frequency)):
        if not isinstance(value, str) or not value:
            raise RiskMeasureError(f"{name} must be a non-empty string")

    n = len(portfolio)
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION

        if n < 2:
            alpha: Decimal | None = None
            beta: Decimal | None = None
        else:
            mean_p = sum(portfolio, Decimal("0")) / Decimal(n)
            mean_b = sum(benchmark, Decimal("0")) / Decimal(n)

            covariance = sum(
                ((p - mean_p) * (b - mean_b) for p, b in zip(portfolio, benchmark)),
                Decimal("0"),
            ) / Decimal(n)
            variance_b = sum(((b - mean_b) ** 2 for b in benchmark), Decimal("0")) / Decimal(n)

            if variance_b == 0:
                alpha = None
                beta = None
            else:
                beta = covariance / variance_b
                alpha = mean_p - risk_free_rate_per_period - beta * (mean_b - risk_free_rate_per_period)

    return AlphaBetaMetrics(
        benchmark_identity=benchmark_identity,
        frequency=frequency,
        observation_count=n,
        alpha=alpha,
        beta=beta,
    )
