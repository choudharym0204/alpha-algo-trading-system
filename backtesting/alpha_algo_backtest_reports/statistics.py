"""Extended trade statistics for backtest performance reports (P7-004).

These aggregates are the §53 fields the P7-002 engine does *not* already
compute (net profit, loss rate, expectancy, average win/loss, risk/reward,
largest win/loss, consecutive streaks, average trade duration, recovery
factor, total fees, total slippage). Every statistic is a hypothetical
reconstruction of the explicit historical inputs under documented
assumptions; it is not evidence of profitability and implies no forward
performance. Undefined ratios are ``None`` — never 0, never Infinity, never
a crash. All arithmetic is exact ``Decimal`` under ``localcontext`` 28.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, localcontext

from alpha_algo_backtest_engine import DECIMAL_PRECISION, BacktestMetrics, BacktestRun

from alpha_algo_backtest_reports.errors import BacktestReportError

__all__ = [
    "TRADE_STATISTICS_POLICY",
    "TradeStatistics",
    "compute_trade_statistics",
]

TRADE_STATISTICS_POLICY = (
    "Trade statistics aggregate the engine's completed FIFO TradeRecords "
    "only: net_profit is the sum of realized P&L; loss_rate is losses over "
    "trade_count; average_loss and largest_loss are positive magnitudes; "
    "average trade duration is the mean over trades of (max exit fill time - "
    "entry fill time) via the fill-sequence to timestamp join; recovery "
    "factor is net_profit over the currency maximum drawdown. Undefined "
    "ratios are None — never 0, never Infinity, never a crash."
)


def _max_streak(values: tuple[Decimal, ...], predicate: object) -> int:
    best = 0
    current = 0
    for value in values:
        if predicate(value):  # type: ignore[operator]
            current += 1
            if current > best:
                best = current
        else:
            current = 0
    return best


def _average_trade_duration(run: BacktestRun) -> timedelta | None:
    fills = run.fills
    by_sequence = {fill.sequence: fill for fill in fills}
    if len(by_sequence) != len(fills):
        raise BacktestReportError("fill sequences must be unique")

    durations: list[timedelta] = []
    for trade in run.trades:
        if trade.entry_fill_sequence not in by_sequence:
            raise BacktestReportError("trade references an unknown entry fill sequence")
        entry_time = by_sequence[trade.entry_fill_sequence].filled_at
        if not trade.exit_fill_sequences:
            raise BacktestReportError("trade must have at least one exit fill sequence")
        exit_times: list = []
        for sequence in trade.exit_fill_sequences:
            if sequence not in by_sequence:
                raise BacktestReportError("trade references an unknown exit fill sequence")
            exit_times.append(by_sequence[sequence].filled_at)
        exit_time = max(exit_times)
        try:
            duration = exit_time - entry_time
        except TypeError as exc:
            raise BacktestReportError("fill timestamps must share timezone awareness") from exc
        if duration < timedelta(0):
            raise BacktestReportError("exit fill must not precede the entry fill")
        durations.append(duration)

    if not durations:
        return None
    return sum(durations, timedelta(0)) / len(durations)


@dataclass(frozen=True)
class TradeStatistics:
    """Report-only trade aggregates for one backtest run.

    Trade statistics are a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; they are not evidence of
    profitability and imply no forward performance.
    """

    net_profit: Decimal
    loss_rate: Decimal | None
    expectancy: Decimal | None
    avg_win: Decimal | None
    avg_loss: Decimal | None
    risk_reward_ratio: Decimal | None
    largest_win: Decimal | None
    largest_loss: Decimal | None
    max_consecutive_wins: int
    max_consecutive_losses: int
    average_trade_duration: timedelta | None
    recovery_factor: Decimal | None
    total_fees: Decimal
    total_slippage: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.net_profit, Decimal) or not self.net_profit.is_finite():
            raise BacktestReportError("TradeStatistics.net_profit must be a finite Decimal")
        for name, value in (
            ("loss_rate", self.loss_rate),
            ("expectancy", self.expectancy),
            ("avg_win", self.avg_win),
            ("avg_loss", self.avg_loss),
            ("risk_reward_ratio", self.risk_reward_ratio),
            ("largest_win", self.largest_win),
            ("largest_loss", self.largest_loss),
            ("recovery_factor", self.recovery_factor),
        ):
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite()):
                raise BacktestReportError(f"TradeStatistics.{name} must be a finite Decimal or None")
        if self.avg_win is not None and self.avg_win < 0:
            raise BacktestReportError("TradeStatistics.avg_win must be non-negative")
        if self.avg_loss is not None and self.avg_loss < 0:
            raise BacktestReportError("TradeStatistics.avg_loss must be non-negative")
        if self.largest_win is not None and self.largest_win < 0:
            raise BacktestReportError("TradeStatistics.largest_win must be non-negative")
        if self.largest_loss is not None and self.largest_loss < 0:
            raise BacktestReportError("TradeStatistics.largest_loss must be non-negative")
        for name, value in (("max_consecutive_wins", self.max_consecutive_wins), ("max_consecutive_losses", self.max_consecutive_losses)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise BacktestReportError(f"TradeStatistics.{name} must be a non-negative int")
        if self.average_trade_duration is not None and not isinstance(self.average_trade_duration, timedelta):
            raise BacktestReportError("TradeStatistics.average_trade_duration must be a timedelta or None")
        for name, value in (("total_fees", self.total_fees), ("total_slippage", self.total_slippage)):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise BacktestReportError(f"TradeStatistics.{name} must be a non-negative finite Decimal")


def compute_trade_statistics(
    *,
    run: BacktestRun,
    metrics: BacktestMetrics,
    max_drawdown_dollar: Decimal,
) -> TradeStatistics:
    """Compute the report-only trade aggregates for a run (pure, deterministic).

    Trade statistics are a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; they are not evidence of
    profitability. Raises :class:`BacktestReportError` on a trade that
    references an unknown fill or on a malformed input.
    """
    if not isinstance(run, BacktestRun):
        raise BacktestReportError("run must be a BacktestRun")
    if not isinstance(metrics, BacktestMetrics):
        raise BacktestReportError("metrics must be a BacktestMetrics")
    if not isinstance(max_drawdown_dollar, Decimal) or not max_drawdown_dollar.is_finite() or max_drawdown_dollar < 0:
        raise BacktestReportError("max_drawdown_dollar must be a non-negative finite Decimal")

    trades = run.trades
    trade_count = len(trades)
    pnl = tuple(trade.realized_pnl for trade in trades)

    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION

        net_profit = sum(pnl, Decimal("0"))

        wins = metrics.wins
        losses = metrics.losses
        gross_profit = metrics.gross_profit
        gross_loss = metrics.gross_loss

        loss_rate = Decimal(losses) / Decimal(trade_count) if trade_count > 0 else None
        expectancy = net_profit / Decimal(trade_count) if trade_count > 0 else None
        avg_win = gross_profit / Decimal(wins) if wins > 0 else None
        avg_loss = gross_loss / Decimal(losses) if losses > 0 else None
        risk_reward_ratio = avg_win / avg_loss if (avg_win is not None and avg_loss is not None) else None

        largest_win = max((value for value in pnl if value > 0), default=None)
        largest_loss = max((-value for value in pnl if value < 0), default=None)

        max_consecutive_wins = _max_streak(pnl, lambda value: value > 0)
        max_consecutive_losses = _max_streak(pnl, lambda value: value < 0)

        average_trade_duration = _average_trade_duration(run) if trade_count > 0 else None

        recovery_factor = (
            net_profit / max_drawdown_dollar
            if (trade_count > 0 and max_drawdown_dollar > 0)
            else None
        )

        total_fees = run.total_commission
        total_slippage = run.total_slippage_cost

    return TradeStatistics(
        net_profit=net_profit,
        loss_rate=loss_rate,
        expectancy=expectancy,
        avg_win=avg_win,
        avg_loss=avg_loss,
        risk_reward_ratio=risk_reward_ratio,
        largest_win=largest_win,
        largest_loss=largest_loss,
        max_consecutive_wins=max_consecutive_wins,
        max_consecutive_losses=max_consecutive_losses,
        average_trade_duration=average_trade_duration,
        recovery_factor=recovery_factor,
        total_fees=total_fees,
        total_slippage=total_slippage,
    )
