"""Performance metrics for the backtest simulation engine (P7-002).

Metrics are closed-form pure functions of a :class:`BacktestRun` plus an
injected per-record risk-free rate. Undefined ratios are ``None`` — never 0,
never Infinity, never a crash. Nothing here is annualized: the engine has no
calendar information (records are explicit history with arbitrary spacing),
so no CAGR, annualized Sharpe, or benchmark alpha is computed in v1.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from alpha_algo_backtest_engine.costs import DECIMAL_PRECISION
from alpha_algo_backtest_engine.engine import BacktestRun
from alpha_algo_backtest_engine.errors import BacktestEngineError, BacktestMetricsError

__all__ = ["BacktestMetrics", "compute_metrics"]


@dataclass(frozen=True)
class BacktestMetrics:
    """Core performance metrics for one backtest run.

    Inputs are echoed back (``initial_capital``, ``risk_free_rate_per_period``)
    so the numbers are self-describing. Undefined ratios are ``None``.
    """

    initial_capital: Decimal
    final_equity: Decimal
    total_return: Decimal
    trade_count: int
    wins: int
    losses: int
    breakevens: int
    win_rate: Decimal | None
    gross_profit: Decimal
    gross_loss: Decimal
    profit_factor: Decimal | None
    max_drawdown: Decimal
    sharpe_ratio: Decimal | None
    risk_free_rate_per_period: Decimal


def compute_metrics(
    run: BacktestRun,
    *,
    risk_free_rate_per_period: Decimal,
) -> BacktestMetrics:
    """Compute the core metric set for a run (pure, deterministic).

    ``risk_free_rate_per_period`` is an injected per-record fraction
    (``>= 0``, may be explicitly ``0``); it is required so a Sharpe ratio can
    never be computed with an implied assumption. Metrics raise
    :class:`BacktestMetricsError` if any marked equity is non-positive —
    return and drawdown math is genuinely undefined there, and failing
    loudly is the only honest option.
    """
    if not isinstance(run, BacktestRun):
        raise BacktestEngineError("run must be a BacktestRun")
    if (
        not isinstance(risk_free_rate_per_period, Decimal)
        or not risk_free_rate_per_period.is_finite()
        or risk_free_rate_per_period < 0
    ):
        raise BacktestEngineError("risk_free_rate_per_period must be a non-negative finite Decimal")

    curve = [point.equity for point in run.equity_curve]
    for value in curve:
        if not isinstance(value, Decimal) or not value.is_finite():
            raise BacktestEngineError("equity curve values must be finite Decimals")
        if value <= 0:
            raise BacktestMetricsError("marked equity must stay positive to compute honest metrics")

    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION

        initial_capital = run.initial_capital
        final_equity = curve[-1]
        total_return = (final_equity - initial_capital) / initial_capital

        trades = run.trades
        trade_count = len(trades)
        wins = sum(1 for trade in trades if trade.realized_pnl > 0)
        losses = sum(1 for trade in trades if trade.realized_pnl < 0)
        breakevens = sum(1 for trade in trades if trade.realized_pnl == 0)
        win_rate = Decimal(wins) / Decimal(trade_count) if trade_count > 0 else None

        gross_profit = sum((trade.realized_pnl for trade in trades if trade.realized_pnl > 0), Decimal("0"))
        gross_loss = sum((-trade.realized_pnl for trade in trades if trade.realized_pnl < 0), Decimal("0"))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

        # Max drawdown as a ratio in [0, 1]; the peak is never zero because
        # initial capital is positive and marked equity stays positive.
        peak = curve[0]
        max_drawdown = Decimal("0")
        for value in curve:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        # Per-period Sharpe (population std), explicitly NOT annualized.
        returns = [(curve[k] - curve[k - 1]) / curve[k - 1] for k in range(1, len(curve))]
        if len(returns) < 2:
            sharpe_ratio = None
        else:
            mean = sum(returns, Decimal("0")) / Decimal(len(returns))
            variance = sum(((r - mean) ** 2 for r in returns), Decimal("0")) / Decimal(len(returns))
            std = variance.sqrt()
            sharpe_ratio = None if std == 0 else (mean - risk_free_rate_per_period) / std

    return BacktestMetrics(
        initial_capital=initial_capital,
        final_equity=final_equity,
        total_return=total_return,
        trade_count=trade_count,
        wins=wins,
        losses=losses,
        breakevens=breakevens,
        win_rate=win_rate,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        risk_free_rate_per_period=risk_free_rate_per_period,
    )
