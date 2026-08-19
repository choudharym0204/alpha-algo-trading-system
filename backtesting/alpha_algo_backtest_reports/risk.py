"""Non-annualized risk ratios for backtest performance reports (P7-004).

Sortino and Calmar are pure, deterministic functions of a
:class:`BacktestRun`'s per-period returns and the engine's already-computed
``total_return`` / ``max_drawdown``. Every ratio is a hypothetical
reconstruction of the explicit historical inputs under documented
assumptions; it is not evidence of profitability and implies no forward
performance. Nothing here is annualized (consistent with the engine's
per-period Sharpe and no-calendar stance), and undefined ratios are ``None``
— never 0, never Infinity, never a crash.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from alpha_algo_backtest_engine import DECIMAL_PRECISION, BacktestRun, compute_metrics

from alpha_algo_backtest_reports.curves import (
    _validate_equity_curve,
    compute_downside_deviation,
    compute_period_returns,
)
from alpha_algo_backtest_reports.errors import BacktestReportError

__all__ = [
    "RISK_METRICS_POLICY",
    "RiskMetrics",
    "compute_calmar_ratio",
    "compute_risk_metrics",
    "compute_sortino_ratio",
]

RISK_METRICS_POLICY = (
    "Sortino is (mean per-period return - risk-free rate) / downside "
    "deviation, where downside deviation is the population semi-deviation of "
    "per-period returns against a zero target. Calmar is total_return / "
    "max_drawdown. Both are per-run (non-annualized) and are None when their "
    "denominator is zero or fewer than two returns exist."
)


def _validate_rf(risk_free_rate_per_period: Decimal) -> None:
    if (
        not isinstance(risk_free_rate_per_period, Decimal)
        or not risk_free_rate_per_period.is_finite()
        or risk_free_rate_per_period < 0
    ):
        raise BacktestReportError("risk_free_rate_per_period must be a non-negative finite Decimal")


def _validate_returns(returns: tuple[Decimal, ...]) -> None:
    if not isinstance(returns, tuple):
        raise BacktestReportError("returns must be a tuple of Decimal")
    for value in returns:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise BacktestReportError("returns must contain only finite Decimals")


@dataclass(frozen=True)
class RiskMetrics:
    """Non-annualized risk ratios for one backtest run.

    Risk metrics are a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; they are not evidence of
    profitability and imply no forward performance. Undefined ratios are
    ``None``.
    """

    sortino_ratio: Decimal | None
    calmar_ratio: Decimal | None

    def __post_init__(self) -> None:
        for name, value in (("sortino_ratio", self.sortino_ratio), ("calmar_ratio", self.calmar_ratio)):
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
                raise BacktestReportError(f"RiskMetrics.{name} must be a finite Decimal or None")


def compute_sortino_ratio(
    returns: tuple[Decimal, ...],
    *,
    risk_free_rate_per_period: Decimal,
) -> Decimal | None:
    """Return the non-annualized Sortino ratio over the given per-period returns.

    The Sortino ratio is a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; it is not evidence of
    profitability. It is ``None`` when there are fewer than two returns or
    when the downside deviation is zero.
    """
    _validate_returns(returns)
    _validate_rf(risk_free_rate_per_period)
    if len(returns) < 2:
        return None
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        mean = sum(returns, Decimal("0")) / Decimal(len(returns))
        downside = compute_downside_deviation(returns)
        if downside == 0:
            return None
        return (mean - risk_free_rate_per_period) / downside


def compute_calmar_ratio(*, total_return: Decimal, max_drawdown: Decimal) -> Decimal | None:
    """Return the non-annualized Calmar ratio (total_return / max_drawdown).

    The Calmar ratio is a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; it is not evidence of
    profitability. It is ``None`` when ``max_drawdown`` is zero.
    """
    if not isinstance(total_return, Decimal) or not total_return.is_finite():
        raise BacktestReportError("total_return must be a finite Decimal")
    if not isinstance(max_drawdown, Decimal) or not max_drawdown.is_finite():
        raise BacktestReportError("max_drawdown must be a finite Decimal")
    if max_drawdown < 0 or max_drawdown > 1:
        raise BacktestReportError("max_drawdown must be in [0, 1]")
    if max_drawdown == 0:
        return None
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        return total_return / max_drawdown


def compute_risk_metrics(
    run: BacktestRun,
    *,
    risk_free_rate_per_period: Decimal,
) -> RiskMetrics:
    """Compute Sortino and Calmar for a run (pure, deterministic).

    Risk metrics are a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; they are not evidence of
    profitability. Raises :class:`BacktestReportMetricsError` if any marked
    equity is non-positive.
    """
    if not isinstance(run, BacktestRun):
        raise BacktestReportError("run must be a BacktestRun")
    _validate_rf(risk_free_rate_per_period)
    _validate_equity_curve(run.equity_curve)

    returns = compute_period_returns(run.equity_curve)
    return_values = tuple(point.value for point in returns)
    metrics = compute_metrics(run, risk_free_rate_per_period=risk_free_rate_per_period)
    sortino = compute_sortino_ratio(return_values, risk_free_rate_per_period=risk_free_rate_per_period)
    calmar = compute_calmar_ratio(total_return=metrics.total_return, max_drawdown=metrics.max_drawdown)
    return RiskMetrics(sortino_ratio=sortino, calmar_ratio=calmar)
