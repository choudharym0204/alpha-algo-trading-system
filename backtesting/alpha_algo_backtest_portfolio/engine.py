"""Multi-symbol portfolio simulation engine (P16).

A pure, deterministic, long-only portfolio simulator that composes the
existing single-instrument fill/cost semantics over a shared cash pool. It
does **not** create a second production Portfolio/P&L engine: it reuses the
verified engine fill resolution and FIFO ledger per symbol, adds a shared
capital pool (reserved-cash floor + per-symbol budget caps), and merges every
symbol into one deterministic global timeline.

Determinism: the global timeline is sorted by ``(timestamp, symbol)``; ties
across symbols at the same timestamp are ordered by symbol name, so the
result is independent of the caller's input order, hash seeds, and process
scheduling. Intents are anchored per symbol at the first record of that
symbol strictly after ``decided_at`` (same no-look-ahead fill timing as the
single-symbol engine).

Long-only: BUY opens/increases, SELL decreases/closes; the engine's
INSUFFICIENT_POSITION guard prevents short/flip (the production Position
Engine's stance is preserved, never silently bypassed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from alpha_algo_contracts import MarketCandle, MarketTick

from alpha_algo_backtesting import BacktestTradingMode

from alpha_algo_backtest_engine import (
    DECIMAL_PRECISION,
    CostModel,
    FillOutcome,
    FillRecord,
    IntentSide,
    OrderIntent,
    UnfilledReason,
)
from alpha_algo_backtest_engine.fills import FillEvaluation, evaluate_fill
from alpha_algo_backtest_engine.ledger import TradeRecord, _FifoLedger

from alpha_algo_backtest_portfolio.capital import CapitalAllocation
from alpha_algo_backtest_portfolio.errors import PortfolioBacktestError
from alpha_algo_backtest_portfolio.inputs import PortfolioInput

__all__ = [
    "PORTFOLIO_EQUITY_MARK_POLICY",
    "PORTFOLIO_FILL_TIMING_POLICY",
    "PortfolioEquityPoint",
    "PortfolioIntent",
    "PortfolioResult",
    "PortfolioTrade",
    "run_portfolio_backtest",
]

PORTFOLIO_FILL_TIMING_POLICY = (
    "An intent fills at the first record of its own symbol strictly after "
    "its decided_at (identical to the single-symbol engine). The global "
    "timeline is (timestamp, symbol)-sorted; simultaneous cross-symbol "
    "events are ordered by symbol name, never by scheduling."
)

PORTFOLIO_EQUITY_MARK_POLICY = (
    "Portfolio equity is marked at every global record: cash + sum over "
    "symbols of (position * last observed mark price for that symbol). A "
    "symbol's mark is its most recent record price (candle close / tick "
    "ltp); no future record ever contributes to the mark."
)


def _record_timestamp(record: MarketCandle | MarketTick) -> datetime:
    if isinstance(record, MarketCandle):
        return record.candle_start
    return record.timestamp


def _mark_price(record: MarketCandle | MarketTick) -> Decimal:
    if isinstance(record, MarketCandle):
        price = record.close_price
    else:
        price = record.ltp
    if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
        raise PortfolioBacktestError("mark price must be a positive finite Decimal")
    return price


@dataclass(frozen=True)
class PortfolioIntent:
    """A caller-decided order intent tagged with its target symbol."""

    symbol: str
    intent: OrderIntent

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol:
            raise PortfolioBacktestError("symbol must be a non-empty string")
        if not isinstance(self.intent, OrderIntent):
            raise PortfolioBacktestError("intent must be an OrderIntent")


@dataclass(frozen=True)
class PortfolioTrade:
    """One completed FIFO round trip, tagged with its symbol."""

    symbol: str
    trade: TradeRecord

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol:
            raise PortfolioBacktestError("symbol must be a non-empty string")
        if not isinstance(self.trade, TradeRecord):
            raise PortfolioBacktestError("trade must be a TradeRecord")


@dataclass(frozen=True)
class PortfolioEquityPoint:
    """One marked portfolio equity value at one global record timestamp."""

    timestamp: datetime
    equity: Decimal


@dataclass(frozen=True)
class PortfolioResult:
    """The complete, immutable outcome of one multi-symbol portfolio run."""

    mode: BacktestTradingMode
    input_sha256: str
    dataset_id: str
    source: str
    initial_capital: Decimal
    reserved_cash: Decimal
    cost_model: CostModel
    symbols: tuple[str, ...]
    intents: tuple[PortfolioIntent, ...]
    outcomes: tuple[FillOutcome, ...]
    trades: tuple[PortfolioTrade, ...]
    equity_curve: tuple[PortfolioEquityPoint, ...]

    def __post_init__(self) -> None:
        if self.mode is not BacktestTradingMode.BACKTEST:
            raise PortfolioBacktestError("portfolio runs are BACKTEST-mode only")
        if not isinstance(self.initial_capital, Decimal) or not self.initial_capital.is_finite() or self.initial_capital <= 0:
            raise PortfolioBacktestError("initial_capital must be a positive finite Decimal")
        if not isinstance(self.reserved_cash, Decimal) or not self.reserved_cash.is_finite() or self.reserved_cash < 0:
            raise PortfolioBacktestError("reserved_cash must be a non-negative finite Decimal")
        if not isinstance(self.cost_model, CostModel):
            raise PortfolioBacktestError("cost_model must be a CostModel")
        if not isinstance(self.symbols, tuple) or not self.symbols:
            raise PortfolioBacktestError("symbols must be a non-empty tuple")
        if not isinstance(self.intents, tuple) or not all(isinstance(i, PortfolioIntent) for i in self.intents):
            raise PortfolioBacktestError("intents must be a tuple of PortfolioIntent")
        if not isinstance(self.outcomes, tuple) or not all(isinstance(o, FillOutcome) for o in self.outcomes):
            raise PortfolioBacktestError("outcomes must be a tuple of FillOutcome")
        if len(self.outcomes) != len(self.intents):
            raise PortfolioBacktestError("outcomes must be 1:1 with intents")
        if not isinstance(self.trades, tuple) or not all(isinstance(t, PortfolioTrade) for t in self.trades):
            raise PortfolioBacktestError("trades must be a tuple of PortfolioTrade")
        if not isinstance(self.equity_curve, tuple) or not self.equity_curve:
            raise PortfolioBacktestError("equity_curve must be a non-empty tuple of PortfolioEquityPoint")
        if not all(isinstance(p, PortfolioEquityPoint) for p in self.equity_curve):
            raise PortfolioBacktestError("equity_curve entries must be PortfolioEquityPoint")
        for point in self.equity_curve:
            if not isinstance(point.equity, Decimal) or not point.equity.is_finite():
                raise PortfolioBacktestError("equity values must be finite Decimals")

    @property
    def fills(self) -> tuple[FillRecord, ...]:
        return tuple(outcome.fill for outcome in self.outcomes if outcome.filled and outcome.fill is not None)

    @property
    def final_equity(self) -> Decimal:
        return self.equity_curve[-1].equity

    @property
    def total_commission(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            return sum((fill.commission_amount for fill in self.fills), Decimal("0"))

    @property
    def total_slippage_cost(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = DECIMAL_PRECISION
            return sum((fill.slippage_per_share * fill.quantity for fill in self.fills), Decimal("0"))


def run_portfolio_backtest(
    *,
    portfolio: PortfolioInput,
    intents: tuple[PortfolioIntent, ...],
    cost_model: CostModel,
    allocation: CapitalAllocation,
) -> PortfolioResult:
    """Simulate one deterministic multi-symbol portfolio run (pure).

    Identical (portfolio, intents, cost model, allocation) yield an identical
    :class:`PortfolioResult`. The engine reuses the single-symbol fill/cost/
    FIFO semantics, shares one cash pool, and orders simultaneous cross-symbol
    events by symbol name.
    """
    if not isinstance(portfolio, PortfolioInput):
        raise PortfolioBacktestError("portfolio must be a PortfolioInput")
    if not isinstance(intents, tuple) or not all(isinstance(i, PortfolioIntent) for i in intents):
        raise PortfolioBacktestError("intents must be a tuple of PortfolioIntent")
    if not isinstance(cost_model, CostModel):
        raise PortfolioBacktestError("cost_model must be a CostModel")
    if not isinstance(allocation, CapitalAllocation):
        raise PortfolioBacktestError("allocation must be a CapitalAllocation")

    symbols = portfolio.symbols
    inputs_by_symbol = portfolio.symbol_inputs

    for item in intents:
        if item.symbol not in inputs_by_symbol:
            raise PortfolioBacktestError(f"intent references unknown symbol {item.symbol!r}")

    # Group intents by symbol, sort each group by decided_at (ties rejected).
    by_symbol: dict[str, list[tuple[int, OrderIntent]]] = {s: [] for s in symbols}
    for global_index, item in enumerate(intents):
        by_symbol[item.symbol].append((global_index, item.intent))
    for symbol in symbols:
        group = by_symbol[symbol]
        group.sort(key=lambda entry: entry[1].decided_at)
        for index in range(1, len(group)):
            if group[index][1].decided_at <= group[index - 1][1].decided_at:
                raise PortfolioBacktestError(
                    f"intents for symbol {symbol!r} must be sorted by strictly ascending decided_at"
                )

    # Anchor each intent at the first record of its symbol strictly after
    # decided_at (monotonic per-symbol cursor, identical to the single engine).
    anchored: dict[str, list[list[int]]] = {
        s: [[] for _ in range(len(inputs_by_symbol[s].records))] for s in symbols
    }
    outcomes: list[FillOutcome | None] = [None] * len(intents)
    for symbol in symbols:
        records = inputs_by_symbol[symbol].records
        cursor = 0
        for global_index, intent in by_symbol[symbol]:
            while cursor < len(records) and _record_timestamp(records[cursor]) <= intent.decided_at:
                cursor += 1
            if cursor < len(records):
                anchored[symbol][cursor].append(global_index)
            else:
                outcomes[global_index] = FillOutcome(
                    intent_index=global_index,
                    filled=False,
                    reason=UnfilledReason.NO_RECORD_AFTER_DECISION.value,
                )

    # Build the deterministic global timeline: (timestamp, symbol, local_index).
    timeline: list[tuple[datetime, str, int, MarketCandle | MarketTick]] = []
    for symbol in symbols:
        for local_index, record in enumerate(inputs_by_symbol[symbol].records):
            timeline.append((_record_timestamp(record), symbol, local_index, record))
    timeline.sort(key=lambda entry: (entry[0], entry[1]))

    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION

        cash = allocation.initial_capital
        position: dict[str, Decimal] = {s: Decimal("0") for s in symbols}
        last_mark: dict[str, Decimal] = {}
        sequence = 0
        trades: list[PortfolioTrade] = []
        equity_points: list[PortfolioEquityPoint] = []
        ledgers: dict[str, _FifoLedger] = {s: _FifoLedger() for s in symbols}

        for global_record_index, (timestamp, symbol, _local_index, record) in enumerate(timeline):
            last_mark[symbol] = _mark_price(record)

            for global_intent_index in anchored[symbol][_local_index]:
                intent = intents[global_intent_index].intent
                evaluation = evaluate_fill(
                    intent=intent,
                    record=record,
                    record_index=global_record_index,
                    cash=cash,
                    position=position[symbol],
                    cost_model=cost_model,
                    sequence=sequence,
                    intent_index=global_intent_index,
                )

                # Reserved-cash floor: a BUY that would dip cash below the
                # reserved amount is refused (capital allocation, not margin).
                if evaluation.fill is not None and evaluation.cash < allocation.reserved_cash:
                    evaluation = FillEvaluation(
                        outcome=FillOutcome(
                            intent_index=global_intent_index,
                            filled=False,
                            reason=UnfilledReason.INSUFFICIENT_CASH.value,
                        ),
                        fill=None,
                        cash=cash,
                        position=position[symbol],
                    )

                # Per-symbol budget cap: a BUY whose gross notional exceeds the
                # symbol budget is refused.
                if evaluation.fill is not None and evaluation.fill.side is IntentSide.BUY:
                    budget = allocation.budget_for(symbol)
                    if budget is not None and evaluation.fill.gross_value > budget:
                        evaluation = FillEvaluation(
                            outcome=FillOutcome(
                                intent_index=global_intent_index,
                                filled=False,
                                reason=UnfilledReason.INSUFFICIENT_CASH.value,
                            ),
                            fill=None,
                            cash=cash,
                            position=position[symbol],
                        )

                outcomes[global_intent_index] = evaluation.outcome
                if evaluation.fill is not None:
                    sequence += 1
                    if evaluation.fill.side is IntentSide.BUY:
                        ledgers[symbol].open_lot(evaluation.fill)
                    else:
                        trades.extend(
                            PortfolioTrade(symbol=symbol, trade=trade)
                            for trade in ledgers[symbol].close_lots(evaluation.fill)
                        )
                    cash = evaluation.cash
                    position[symbol] = evaluation.position

            # Mark portfolio equity after this record's fills.
            market_value = Decimal("0")
            for s in symbols:
                if position[s] != 0:
                    mark = last_mark.get(s)
                    if mark is None:
                        raise PortfolioBacktestError("internal error: position without a mark")
                    market_value += position[s] * mark
            equity_points.append(PortfolioEquityPoint(timestamp=timestamp, equity=cash + market_value))

    if any(outcome is None for outcome in outcomes):
        raise PortfolioBacktestError("internal error: every intent must have exactly one outcome")
    final_outcomes = tuple(outcomes)  # type: ignore[arg-type]

    return PortfolioResult(
        mode=BacktestTradingMode.BACKTEST,
        input_sha256=portfolio.content_sha256,
        dataset_id=portfolio.dataset_id,
        source=portfolio.source,
        initial_capital=allocation.initial_capital,
        reserved_cash=allocation.reserved_cash,
        cost_model=cost_model,
        symbols=symbols,
        intents=tuple(intents),
        outcomes=final_outcomes,
        trades=tuple(trades),
        equity_curve=tuple(equity_points),
    )
