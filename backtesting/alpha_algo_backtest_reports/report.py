"""Backtest report assembly (P7-004).

The report layer composes the verified P7-001 foundation and P7-002 engine
into a single immutable :class:`BacktestReport`: base metrics (single source
of truth), extended trade statistics, non-annualized risk ratios, a drawdown
curve, period-bucketed performance, and a partial §48 trade reconstruction.
A backtest report is a hypothetical reconstruction of the explicit
historical inputs under documented cost, fill, and parameter assumptions; it
is not evidence of profitability and implies no forward performance. The
package performs no execution, no persistence, no regime analysis, no
signal/strategy runtime, and no live/broker surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from alpha_algo_backtesting import BacktestTradingMode

from alpha_algo_backtest_engine import (
    DECIMAL_PRECISION,
    BacktestMetrics,
    BacktestRun,
    CostModel,
    EquityPoint,
    compute_metrics,
)

from alpha_algo_backtest_reports.curves import (
    DrawdownPoint,
    PeriodBucket,
    PeriodGranularity,
    ReturnPoint,
    _validate_equity_curve,
    bucket_performance,
    compute_drawdown_series,
    compute_period_returns,
)
from alpha_algo_backtest_reports.errors import BacktestReportError
from alpha_algo_backtest_reports.risk import (
    RiskMetrics,
    _validate_rf,
    compute_calmar_ratio,
    compute_sortino_ratio,
)
from alpha_algo_backtest_reports.statistics import TradeStatistics, compute_trade_statistics

__all__ = [
    "REPORT_LIMITATIONS",
    "REPORT_SCOPE_POLICY",
    "TRADE_RECONSTRUCTION_POLICY",
    "BacktestReport",
    "TradeReconstruction",
    "build_report",
    "build_trade_reconstructions",
]

REPORT_SCOPE_POLICY = (
    "A backtest report is a pure, deterministic reconstruction of a single "
    "explicit BacktestRun plus an injected per-period risk-free rate: it "
    "reads no wall clock, uses no randomness, performs no I/O, embeds no "
    "data, persists nothing, and performs no execution, regime analysis, "
    "signal generation, or live/broker action. Results are hypothetical "
    "reconstructions under documented assumptions, not evidence of "
    "profitability."
)

TRADE_RECONSTRUCTION_POLICY = (
    "Reconstructed trades join TradeRecord.entry_fill_sequence and "
    "exit_fill_sequences to FillRecord.filled_at for timestamps, and to the "
    "entry/exit fill for prices, quantity, fees, and slippage. Fields the "
    "engine does not record (symbol, MFE/MAE, entry/exit reason, stop loss, "
    "target) are None — never fabricated. Signals are not modeled: any "
    "caller tag surfaces as entry_label/exit_label from OrderIntent.label."
)

REPORT_LIMITATIONS = (
    "single-instrument (P7-001 enforces one symbol/kind; the run carries dataset_id/source, not a symbol)",
    "long-only (the engine is BUY-opens / SELL-closes with a single non-negative position)",
    "non-annualized (Sharpe/Sortino/Calmar are per-record; no calendar model exists)",
    "no regime breakdown (regime is not modeled by the engine)",
    "MFE/MAE, entry/exit reason, stop loss, and target are None (not recorded by the engine)",
)


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


@dataclass(frozen=True)
class TradeReconstruction:
    """One reconstructed round trip from entry fill to exit fill(s).

    A reconstructed trade is a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; it is not evidence of
    profitability and implies no forward performance.
    """

    trade_id: int
    side: str
    symbol: str | None
    timeframe: str | None
    entry_timestamp: datetime
    entry_price: Decimal
    exit_timestamp: datetime
    exit_price: Decimal
    quantity: Decimal
    entry_label: str | None
    exit_label: str | None
    entry_reason: str | None
    exit_reason: str | None
    stop_loss: Decimal | None
    target: Decimal | None
    gross_pnl: Decimal
    net_pnl: Decimal
    fees: Decimal
    entry_slippage: Decimal
    exit_slippage: Decimal | None
    slippage: Decimal | None
    mfe: Decimal | None
    mae: Decimal | None

    def __post_init__(self) -> None:
        if not isinstance(self.trade_id, int) or isinstance(self.trade_id, bool) or self.trade_id < 0:
            raise BacktestReportError("TradeReconstruction.trade_id must be a non-negative int")
        if not isinstance(self.side, str) or not self.side:
            raise BacktestReportError("TradeReconstruction.side must be a non-empty string")
        for name, value in (
            ("symbol", self.symbol),
            ("timeframe", self.timeframe),
            ("entry_label", self.entry_label),
            ("exit_label", self.exit_label),
            ("entry_reason", self.entry_reason),
            ("exit_reason", self.exit_reason),
        ):
            if value is not None and not isinstance(value, str):
                raise BacktestReportError(f"TradeReconstruction.{name} must be a string or None")
        for name, value in (("entry_timestamp", self.entry_timestamp), ("exit_timestamp", self.exit_timestamp)):
            if not isinstance(value, datetime) or not _is_timezone_aware(value):
                raise BacktestReportError(f"TradeReconstruction.{name} must be timezone-aware")
        if self.entry_timestamp > self.exit_timestamp:
            raise BacktestReportError("TradeReconstruction entry must not follow exit")
        for name, value in (
            ("entry_price", self.entry_price),
            ("exit_price", self.exit_price),
            ("quantity", self.quantity),
        ):
            if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
                raise BacktestReportError(f"TradeReconstruction.{name} must be a positive finite Decimal")
        for name, value in (("stop_loss", self.stop_loss), ("target", self.target)):
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite() or value <= 0):
                raise BacktestReportError(f"TradeReconstruction.{name} must be a positive finite Decimal or None")
        for name, value in (("gross_pnl", self.gross_pnl), ("net_pnl", self.net_pnl)):
            if not isinstance(value, Decimal) or not value.is_finite():
                raise BacktestReportError(f"TradeReconstruction.{name} must be a finite Decimal")
        for name, value in (
            ("fees", self.fees),
            ("entry_slippage", self.entry_slippage),
        ):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise BacktestReportError(f"TradeReconstruction.{name} must be a non-negative finite Decimal")
        for name, value in (("exit_slippage", self.exit_slippage), ("slippage", self.slippage)):
            if value is not None and (not isinstance(value, Decimal) or not value.is_finite() or value < 0):
                raise BacktestReportError(f"TradeReconstruction.{name} must be a non-negative finite Decimal or None")
        if (self.exit_slippage is None) != (self.slippage is None):
            raise BacktestReportError("TradeReconstruction exit_slippage and slippage must be None together")
        if self.mfe is not None and (not isinstance(self.mfe, Decimal) or not self.mfe.is_finite() or self.mfe < 0):
            raise BacktestReportError("TradeReconstruction.mfe must be a non-negative finite Decimal or None")
        if self.mae is not None and (not isinstance(self.mae, Decimal) or not self.mae.is_finite() or self.mae > 0):
            raise BacktestReportError("TradeReconstruction.mae must be a non-positive finite Decimal or None")


@dataclass(frozen=True)
class BacktestReport:
    """The immutable, self-describing report for one backtest run.

    A backtest report is a hypothetical reconstruction of the explicit
    historical inputs under documented cost, fill, and parameter
    assumptions; it is not evidence of profitability and implies no forward
    performance.
    """

    input_sha256: str
    dataset_id: str
    source: str
    mode: BacktestTradingMode
    symbol: str | None
    timeframe: str | None
    initial_capital: Decimal
    cost_model: CostModel
    risk_free_rate_per_period: Decimal
    metrics: BacktestMetrics
    statistics: TradeStatistics
    risk: RiskMetrics
    trades: tuple[TradeReconstruction, ...]
    equity_curve: tuple[EquityPoint, ...]
    returns: tuple[ReturnPoint, ...]
    drawdowns: tuple[DrawdownPoint, ...]
    daily_buckets: tuple[PeriodBucket, ...]
    monthly_buckets: tuple[PeriodBucket, ...]
    yearly_buckets: tuple[PeriodBucket, ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for name, value in (("input_sha256", self.input_sha256), ("dataset_id", self.dataset_id), ("source", self.source)):
            if not isinstance(value, str) or not value:
                raise BacktestReportError(f"BacktestReport.{name} must be a non-empty string")
        if not isinstance(self.mode, BacktestTradingMode):
            raise BacktestReportError("BacktestReport.mode must be a BacktestTradingMode")
        for name, value in (("symbol", self.symbol), ("timeframe", self.timeframe)):
            if value is not None and not isinstance(value, str):
                raise BacktestReportError(f"BacktestReport.{name} must be a string or None")
        if not isinstance(self.initial_capital, Decimal) or not self.initial_capital.is_finite() or self.initial_capital <= 0:
            raise BacktestReportError("BacktestReport.initial_capital must be a positive finite Decimal")
        if not isinstance(self.cost_model, CostModel):
            raise BacktestReportError("BacktestReport.cost_model must be a CostModel")
        if not isinstance(self.risk_free_rate_per_period, Decimal) or not self.risk_free_rate_per_period.is_finite() or self.risk_free_rate_per_period < 0:
            raise BacktestReportError("BacktestReport.risk_free_rate_per_period must be a non-negative finite Decimal")
        if not isinstance(self.metrics, BacktestMetrics):
            raise BacktestReportError("BacktestReport.metrics must be a BacktestMetrics")
        if not isinstance(self.statistics, TradeStatistics):
            raise BacktestReportError("BacktestReport.statistics must be a TradeStatistics")
        if not isinstance(self.risk, RiskMetrics):
            raise BacktestReportError("BacktestReport.risk must be a RiskMetrics")
        if not isinstance(self.trades, tuple) or not all(isinstance(item, TradeReconstruction) for item in self.trades):
            raise BacktestReportError("BacktestReport.trades must be a tuple of TradeReconstruction")
        if not isinstance(self.equity_curve, tuple) or not self.equity_curve:
            raise BacktestReportError("BacktestReport.equity_curve must be a non-empty tuple of EquityPoint")
        for name, value in (
            ("returns", self.returns),
            ("drawdowns", self.drawdowns),
            ("daily_buckets", self.daily_buckets),
            ("monthly_buckets", self.monthly_buckets),
            ("yearly_buckets", self.yearly_buckets),
            ("limitations", self.limitations),
        ):
            if not isinstance(value, tuple):
                raise BacktestReportError(f"BacktestReport.{name} must be a tuple")
        if not all(isinstance(item, str) for item in self.limitations):
            raise BacktestReportError("BacktestReport.limitations must be a tuple of str")


def build_trade_reconstructions(
    *,
    run: BacktestRun,
    symbol: str | None,
    timeframe: str | None,
) -> tuple[TradeReconstruction, ...]:
    """Reconstruct one record per completed trade (§48 partial).

    Reconstructed trades are a hypothetical reconstruction of the explicit
    historical inputs under documented assumptions; they are not evidence of
    profitability. Raises :class:`BacktestReportError` on a malformed join.
    """
    if not isinstance(run, BacktestRun):
        raise BacktestReportError("run must be a BacktestRun")
    if symbol is not None and not isinstance(symbol, str):
        raise BacktestReportError("symbol must be a string or None")
    if timeframe is not None and not isinstance(timeframe, str):
        raise BacktestReportError("timeframe must be a string or None")

    fills = run.fills
    by_sequence = {fill.sequence: fill for fill in fills}
    if len(by_sequence) != len(fills):
        raise BacktestReportError("fill sequences must be unique")

    # Count exit-fill usage so per-trade exit slippage is exact only when the
    # exit fill is exclusive to a single trade (no FIFO split across lots).
    exit_usage: dict[int, int] = {}
    for trade in run.trades:
        for sequence in trade.exit_fill_sequences:
            exit_usage[sequence] = exit_usage.get(sequence, 0) + 1

    intents = run.intents

    def _label(fill_index: int | None) -> str | None:
        if fill_index is None or fill_index < 0 or fill_index >= len(intents):
            return None
        return intents[fill_index].label

    records: list[TradeReconstruction] = []
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION
        for trade in run.trades:
            if trade.entry_fill_sequence not in by_sequence:
                raise BacktestReportError("trade references an unknown entry fill sequence")
            entry_fill = by_sequence[trade.entry_fill_sequence]
            entry_time = entry_fill.filled_at

            exit_fills = []
            for sequence in trade.exit_fill_sequences:
                if sequence not in by_sequence:
                    raise BacktestReportError("trade references an unknown exit fill sequence")
                exit_fills.append(by_sequence[sequence])
            if not exit_fills:
                raise BacktestReportError("trade must have at least one exit fill sequence")
            exit_time = max(fill.filled_at for fill in exit_fills)
            latest_exit_fill = max(exit_fills, key=lambda fill: fill.filled_at)

            fees = trade.entry_cost + trade.exit_cost
            net_pnl = trade.realized_pnl
            gross_pnl = net_pnl + fees
            entry_slippage = entry_fill.slippage_per_share * trade.quantity

            shared = any(exit_usage[sequence] > 1 for sequence in trade.exit_fill_sequences)
            if shared:
                exit_slippage = None
                slippage = None
            else:
                exit_slippage = sum(
                    (fill.slippage_per_share * fill.quantity for fill in exit_fills),
                    Decimal("0"),
                )
                slippage = entry_slippage + exit_slippage

            records.append(
                TradeReconstruction(
                    trade_id=trade.sequence,
                    side="long",
                    symbol=symbol,
                    timeframe=timeframe,
                    entry_timestamp=entry_time,
                    entry_price=trade.entry_price,
                    exit_timestamp=exit_time,
                    exit_price=trade.exit_price,
                    quantity=trade.quantity,
                    entry_label=_label(entry_fill.intent_index),
                    exit_label=_label(latest_exit_fill.intent_index),
                    entry_reason=None,
                    exit_reason=None,
                    stop_loss=None,
                    target=None,
                    gross_pnl=gross_pnl,
                    net_pnl=net_pnl,
                    fees=fees,
                    entry_slippage=entry_slippage,
                    exit_slippage=exit_slippage,
                    slippage=slippage,
                    mfe=None,
                    mae=None,
                )
            )
    return tuple(records)


def build_report(
    run: BacktestRun,
    *,
    risk_free_rate_per_period: Decimal,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> BacktestReport:
    """Build the immutable report for one backtest run (pure, deterministic).

    A backtest report is a hypothetical reconstruction of the explicit
    historical inputs under documented cost, fill, and parameter
    assumptions; it is not evidence of profitability and implies no forward
    performance. Raises :class:`BacktestReportError` for a refused input and
    :class:`BacktestReportMetricsError` for non-positive marked equity.
    """
    if not isinstance(run, BacktestRun):
        raise BacktestReportError("run must be a BacktestRun")
    _validate_rf(risk_free_rate_per_period)
    if symbol is not None and not isinstance(symbol, str):
        raise BacktestReportError("symbol must be a string or None")
    if timeframe is not None and not isinstance(timeframe, str):
        raise BacktestReportError("timeframe must be a string or None")

    # Pre-check equity positivity before delegating to the engine so the
    # report raises its own typed error, never a bare BacktestMetricsError.
    _validate_equity_curve(run.equity_curve)

    metrics = compute_metrics(run, risk_free_rate_per_period=risk_free_rate_per_period)
    returns = compute_period_returns(run.equity_curve)
    return_values = tuple(point.value for point in returns)
    drawdowns = compute_drawdown_series(run.equity_curve)
    max_drawdown_dollar = max((point.drawdown_amount for point in drawdowns), default=Decimal("0"))

    statistics = compute_trade_statistics(
        run=run,
        metrics=metrics,
        max_drawdown_dollar=max_drawdown_dollar,
    )
    sortino = compute_sortino_ratio(return_values, risk_free_rate_per_period=risk_free_rate_per_period)
    calmar = compute_calmar_ratio(total_return=metrics.total_return, max_drawdown=metrics.max_drawdown)
    risk = RiskMetrics(sortino_ratio=sortino, calmar_ratio=calmar)

    trades = build_trade_reconstructions(run=run, symbol=symbol, timeframe=timeframe)
    daily = bucket_performance(run.equity_curve, granularity=PeriodGranularity.DAILY)
    monthly = bucket_performance(run.equity_curve, granularity=PeriodGranularity.MONTHLY)
    yearly = bucket_performance(run.equity_curve, granularity=PeriodGranularity.YEARLY)

    return BacktestReport(
        input_sha256=run.input_sha256,
        dataset_id=run.dataset_id,
        source=run.source,
        mode=run.mode,
        symbol=symbol,
        timeframe=timeframe,
        initial_capital=run.initial_capital,
        cost_model=run.cost_model,
        risk_free_rate_per_period=risk_free_rate_per_period,
        metrics=metrics,
        statistics=statistics,
        risk=risk,
        trades=trades,
        equity_curve=run.equity_curve,
        returns=returns,
        drawdowns=drawdowns,
        daily_buckets=daily,
        monthly_buckets=monthly,
        yearly_buckets=yearly,
        limitations=REPORT_LIMITATIONS,
    )
