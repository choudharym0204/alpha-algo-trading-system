"""Composite advanced metrics for backtest performance reports (P16).

Ties the individual advanced analytics (CAGR, VaR/CVaR, Alpha/Beta) into one
self-describing :class:`AdvancedMetrics` for a :class:`BacktestRun`. The
per-period return series is derived once from the run's equity curve (via the
existing report ``compute_period_returns``) so every constituent metric is
computed over the same observations.

Everything here is a pure, deterministic reconstruction of the explicit
historical inputs under documented assumptions; it is not evidence of
profitability and implies no forward performance. Nothing here is annualized
except CAGR (which uses the caller-supplied ``periods_per_year`` basis).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from alpha_algo_backtest_engine import BacktestRun, EquityPoint
from alpha_algo_backtest_reports.curves import compute_period_returns

from alpha_algo_backtest_analytics.alpha_beta import AlphaBetaMetrics, compute_alpha_beta
from alpha_algo_backtest_analytics.cagr import CagrResult, compute_cagr
from alpha_algo_backtest_analytics.errors import AnalyticsError
from alpha_algo_backtest_analytics.var import VarCvarMetrics, compute_var_cvar

__all__ = ["ADVANCED_METRICS_POLICY", "AdvancedMetrics", "compute_advanced_metrics"]

ADVANCED_METRICS_POLICY = (
    "Advanced metrics derive one per-period return series from the run's "
    "equity curve and compute CAGR (explicit periods_per_year basis), "
    "historical VaR/CVaR (explicit confidence), and Alpha/Beta (explicit "
    "aligned benchmark, optional). All informational; undefined components "
    "are None; non-positive equity raises AnalyticsError."
)


def _require_positive_curve(curve: tuple[EquityPoint, ...]) -> None:
    for point in curve:
        if not isinstance(point, EquityPoint):
            raise AnalyticsError("equity curve entries must be EquityPoint")
        if not isinstance(point.equity, Decimal) or not point.equity.is_finite():
            raise AnalyticsError("equity values must be finite Decimals")
        if point.equity <= 0:
            raise AnalyticsError("marked equity must stay positive to compute advanced metrics")


@dataclass(frozen=True)
class AdvancedMetrics:
    """Composite advanced analytics for one backtest run.

    These are informational reconstructions of the explicit historical
    inputs under documented assumptions; they imply no statistical guarantee
    and no forward performance.
    """

    initial_equity: Decimal
    final_equity: Decimal
    total_return: Decimal
    period_count: int
    periods_per_year: int
    confidence: Decimal
    cagr: CagrResult | None
    var_cvar: VarCvarMetrics | None
    alpha_beta: AlphaBetaMetrics | None

    def __post_init__(self) -> None:
        for name, value in (("initial_equity", self.initial_equity), ("final_equity", self.final_equity)):
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise AnalyticsError(f"{name} must be a positive finite Decimal")
        if not isinstance(self.total_return, Decimal) or not self.total_return.is_finite():
            raise AnalyticsError("total_return must be a finite Decimal")
        if type(self.period_count) is not int or self.period_count < 0:
            raise AnalyticsError("period_count must be a non-negative int")
        if type(self.periods_per_year) is not int or self.periods_per_year < 1:
            raise AnalyticsError("periods_per_year must be at least 1")
        if not isinstance(self.confidence, Decimal) or not (Decimal("0") < self.confidence < Decimal("1")):
            raise AnalyticsError("confidence must be in the open interval (0, 1)")
        for name, value in (("cagr", self.cagr), ("var_cvar", self.var_cvar), ("alpha_beta", self.alpha_beta)):
            if value is not None and not isinstance(value, (CagrResult, VarCvarMetrics, AlphaBetaMetrics)):
                raise AnalyticsError(f"{name} has an invalid type")


def compute_advanced_metrics(
    run: BacktestRun,
    *,
    risk_free_rate_per_period: Decimal,
    periods_per_year: int,
    confidence: Decimal,
    benchmark_returns: tuple[Decimal, ...] | None = None,
    benchmark_identity: str | None = None,
    frequency: str | None = None,
) -> AdvancedMetrics:
    """Compute the composite advanced metric set for a run (pure).

    ``benchmark_returns`` enables Alpha/Beta; when omitted Alpha/Beta are
    ``None``. The benchmark series, if provided, must be aligned with the
    run's per-period returns (equal length). Raises :class:`AnalyticsError`
    on non-positive equity or out-of-contract inputs.
    """
    if not isinstance(run, BacktestRun):
        raise AnalyticsError("run must be a BacktestRun")
    if (
        not isinstance(risk_free_rate_per_period, Decimal)
        or not risk_free_rate_per_period.is_finite()
        or risk_free_rate_per_period < 0
    ):
        raise AnalyticsError("risk_free_rate_per_period must be a non-negative finite Decimal")
    if type(periods_per_year) is not int or periods_per_year < 1:
        raise AnalyticsError("periods_per_year must be at least 1")
    if not isinstance(confidence, Decimal) or not (Decimal("0") < confidence < Decimal("1")):
        raise AnalyticsError("confidence must be in the open interval (0, 1)")

    curve = run.equity_curve
    _require_positive_curve(curve)

    return_points = compute_period_returns(curve)
    return_values = tuple(point.value for point in return_points)

    cagr = compute_cagr(
        beginning_value=curve[0].equity,
        ending_value=curve[-1].equity,
        periods=len(return_values),
        periods_per_year=periods_per_year,
    )
    var_cvar = compute_var_cvar(return_values, confidence=confidence)

    alpha_beta: AlphaBetaMetrics | None = None
    if benchmark_returns is not None:
        if benchmark_identity is None or frequency is None:
            raise AnalyticsError("benchmark_identity and frequency are required when benchmark_returns is provided")
        alpha_beta = compute_alpha_beta(
            portfolio=return_values,
            benchmark=benchmark_returns,
            risk_free_rate_per_period=risk_free_rate_per_period,
            benchmark_identity=benchmark_identity,
            frequency=frequency,
        )

    total_return = cagr.total_return

    return AdvancedMetrics(
        initial_equity=curve[0].equity,
        final_equity=curve[-1].equity,
        total_return=total_return,
        period_count=len(return_values),
        periods_per_year=periods_per_year,
        confidence=confidence,
        cagr=cagr,
        var_cvar=var_cvar,
        alpha_beta=alpha_beta,
    )
