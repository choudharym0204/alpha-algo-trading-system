"""Backtest run orchestration (P7-002).

``run_backtest`` is a pure, stateless function: identical (input, intents,
cost model, initial capital) yields an identical :class:`BacktestRun` across
runs and hash seeds. It takes no clock, reads no wall clock, performs no
I/O, and never generates order intents, UUIDs, or data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from alpha_algo_contracts import MarketCandle, MarketTick

from alpha_algo_backtesting import BacktestInput, BacktestTradingMode

from alpha_algo_backtest_engine.costs import DECIMAL_PRECISION, CostModel
from alpha_algo_backtest_engine.errors import BacktestEngineError
from alpha_algo_backtest_engine.fills import (
    FillOutcome,
    FillRecord,
    UnfilledReason,
    evaluate_fill,
)
from alpha_algo_backtest_engine.intents import IntentSide, OrderIntent
from alpha_algo_backtest_engine.ledger import TradeRecord, _FifoLedger

__all__ = [
    "EQUITY_MARK_POLICY",
    "BacktestRun",
    "EquityPoint",
    "run_backtest",
]

EQUITY_MARK_POLICY = (
    "Equity is marked at every record — candles at close_price, ticks at ltp "
    "— after applying the fills anchored at that record. With no pre-data "
    "intents the initial point equals initial_capital; the final point is "
    "the terminal mark and feeds final_equity."
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
        raise BacktestEngineError("mark price must be a positive finite Decimal")
    return price


@dataclass(frozen=True)
class EquityPoint:
    """One marked equity value at one record timestamp (never a wall clock)."""

    timestamp: datetime
    equity: Decimal


@dataclass(frozen=True)
class BacktestRun:
    """The complete, immutable outcome of one backtest simulation.

    ``mode`` is pinned to ``BacktestTradingMode.BACKTEST`` (the PaperPosition
    precedent): BACKTEST is structurally the only mode this type can carry.
    """

    mode: BacktestTradingMode
    input_sha256: str
    dataset_id: str
    source: str
    initial_capital: Decimal
    cost_model: CostModel
    intents: tuple[OrderIntent, ...]
    outcomes: tuple[FillOutcome, ...]
    trades: tuple[TradeRecord, ...]
    equity_curve: tuple[EquityPoint, ...]

    def __post_init__(self) -> None:
        if self.mode is not BacktestTradingMode.BACKTEST:
            raise BacktestEngineError("backtest runs are BACKTEST-mode only")
        if (
            not isinstance(self.initial_capital, Decimal)
            or not self.initial_capital.is_finite()
            or self.initial_capital <= 0
        ):
            raise BacktestEngineError("initial_capital must be a positive finite Decimal")
        if not isinstance(self.cost_model, CostModel):
            raise BacktestEngineError("cost_model must be a CostModel")
        if not isinstance(self.intents, tuple) or not all(isinstance(item, OrderIntent) for item in self.intents):
            raise BacktestEngineError("intents must be a tuple of OrderIntent")
        if not isinstance(self.outcomes, tuple) or not all(isinstance(item, FillOutcome) for item in self.outcomes):
            raise BacktestEngineError("outcomes must be a tuple of FillOutcome")
        if len(self.outcomes) != len(self.intents):
            raise BacktestEngineError("outcomes must be 1:1 with intents (nothing silently dropped)")
        if not isinstance(self.trades, tuple) or not all(isinstance(item, TradeRecord) for item in self.trades):
            raise BacktestEngineError("trades must be a tuple of TradeRecord")
        if not isinstance(self.equity_curve, tuple) or not self.equity_curve:
            raise BacktestEngineError("equity_curve must be a non-empty tuple of EquityPoint")
        if not all(isinstance(point, EquityPoint) for point in self.equity_curve):
            raise BacktestEngineError("equity_curve entries must be EquityPoint")
        for point in self.equity_curve:
            if not isinstance(point.equity, Decimal) or not point.equity.is_finite():
                raise BacktestEngineError("equity values must be finite Decimals")

    @property
    def fills(self) -> tuple[FillRecord, ...]:
        """All fills in application order (intent order, since intents are
        strictly ascending and each anchor is processed in record order)."""
        return tuple(
            outcome.fill for outcome in self.outcomes if outcome.filled and outcome.fill is not None
        )

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


def run_backtest(
    *,
    inputs: BacktestInput,
    intents: tuple[OrderIntent, ...],
    cost_model: CostModel,
    initial_capital: Decimal,
) -> BacktestRun:
    """Simulate one deterministic backtest run (pure, stateless).

    Every fill, cost, equity point, and trade is a pure function of the
    explicit historical ``inputs``, the caller-decided ``intents``, the
    ``cost_model``, and ``initial_capital``. Identical arguments yield an
    identical :class:`BacktestRun` across runs and hash seeds.
    """
    if not isinstance(inputs, BacktestInput):
        raise BacktestEngineError("inputs must be a BacktestInput")
    if not isinstance(intents, tuple) or not all(isinstance(item, OrderIntent) for item in intents):
        raise BacktestEngineError("intents must be a tuple of OrderIntent")
    if not isinstance(cost_model, CostModel):
        raise BacktestEngineError("cost_model must be a CostModel")
    if not isinstance(initial_capital, Decimal) or not initial_capital.is_finite() or initial_capital <= 0:
        raise BacktestEngineError("initial_capital must be a positive finite Decimal")
    for index in range(1, len(intents)):
        if intents[index].decided_at <= intents[index - 1].decided_at:
            raise BacktestEngineError(
                "intents must be sorted by strictly ascending decided_at (ties rejected; never reordered)"
            )

    records = inputs.records
    record_count = len(records)

    # The entire simulation runs under a fixed Decimal precision so that a
    # third party mutating the ambient decimal context can never change
    # results (determinism commitment #8).
    with localcontext() as ctx:
        ctx.prec = DECIMAL_PRECISION

        # Anchor each intent at the first record strictly after its decided_at.
        # Records and intents are both ascending, so the cursor is monotonic.
        # Every intent gets exactly one outcome (1:1 accounting): intents with no
        # record strictly after their decided_at are pre-filled UNFILLED.
        cursor = 0
        anchored: list[list[int]] = [[] for _ in range(record_count)]
        outcomes: list[FillOutcome | None] = [None] * len(intents)
        for index, intent in enumerate(intents):
            while cursor < record_count and _record_timestamp(records[cursor]) <= intent.decided_at:
                cursor += 1
            if cursor < record_count:
                anchored[cursor].append(index)
            else:
                outcomes[index] = FillOutcome(
                    intent_index=index,
                    filled=False,
                    reason=UnfilledReason.NO_RECORD_AFTER_DECISION.value,
                )

        cash = initial_capital
        position = Decimal("0")
        sequence = 0
        trades: list[TradeRecord] = []
        equity_points: list[EquityPoint] = []
        ledger = _FifoLedger()

        for record_index, record in enumerate(records):
            for intent_index in anchored[record_index]:
                intent = intents[intent_index]
                evaluation = evaluate_fill(
                    intent=intent,
                    record=record,
                    record_index=record_index,
                    cash=cash,
                    position=position,
                    cost_model=cost_model,
                    sequence=sequence,
                    intent_index=intent_index,
                )
                outcomes[intent_index] = evaluation.outcome
                if evaluation.fill is not None:
                    sequence += 1
                    if intent.side is IntentSide.BUY:
                        ledger.open_lot(evaluation.fill)
                    else:
                        trades.extend(ledger.close_lots(evaluation.fill))
                cash = evaluation.cash
                position = evaluation.position
            equity_points.append(
                EquityPoint(
                    timestamp=_record_timestamp(record),
                    equity=cash + position * _mark_price(record),
                )
            )

    if any(outcome is None for outcome in outcomes):
        raise BacktestEngineError("internal error: every intent must have exactly one outcome")
    final_outcomes: list[FillOutcome] = []
    for outcome in outcomes:
        if outcome is None:
            raise BacktestEngineError("internal error: every intent must have exactly one outcome")
        final_outcomes.append(outcome)

    return BacktestRun(
        mode=BacktestTradingMode.BACKTEST,
        input_sha256=inputs.content_sha256,
        dataset_id=inputs.dataset_id,
        source=inputs.source,
        initial_capital=initial_capital,
        cost_model=cost_model,
        intents=tuple(intents),
        outcomes=tuple(final_outcomes),
        trades=tuple(trades),
        equity_curve=tuple(equity_points),
    )
