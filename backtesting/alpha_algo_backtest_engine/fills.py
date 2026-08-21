"""Deterministic fill resolution for the backtest simulation engine (P7-002).

Fill decisions are pure functions of (intent, anchor record, cash, position,
cost model) under fixed, constant-named policies. The engine never fills at
a price that was not actually quoted, never falls back to a missing quote
leg for a limit execution, and never fills an intent at the record that
decided it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from alpha_algo_contracts import MarketCandle, MarketTick

from alpha_algo_backtest_engine.costs import CostModel, apply_slippage, commission_for
from alpha_algo_backtest_engine.errors import BacktestEngineError
from alpha_algo_backtest_engine.intents import IntentSide, IntentType, OrderIntent

__all__ = [
    "CANDLE_FILL_POLICY",
    "CANDLE_LIMIT_NO_IMPROVEMENT",
    "FILL_TIMING_POLICY",
    "FillEvaluation",
    "FillOutcome",
    "FillRecord",
    "TICK_LIMIT_FILL_POLICY",
    "TICK_MARKET_FILL_POLICY",
    "UnfilledReason",
    "evaluate_fill",
]

FILL_TIMING_POLICY = (
    "An intent fills at the first record strictly after its decided_at. "
    "Same-record fills are impossible (strictly-after), so the record that "
    "decided an intent can never be the record that fills it. An intent with "
    "no record strictly after its decided_at is UNFILLED with "
    "NO_RECORD_AFTER_DECISION."
)

TICK_MARKET_FILL_POLICY = (
    "MARKET fills on ticks use the executable side: a BUY fills at ask when "
    "present, else ltp; a SELL fills at bid when present, else ltp. This "
    "deliberately diverges from P8-001's MARKET-at-last paper reference "
    "snapshot: a backtest consuming real tick quotes pays the spread."
)

TICK_LIMIT_FILL_POLICY = (
    "LIMIT fills on ticks mirror the paper policy: a BUY fills at ask iff "
    "limit_price >= ask; a SELL fills at bid iff limit_price <= bid. A "
    "missing required leg means UNFILLED (NO_EXECUTABLE_ASK / "
    "NO_EXECUTABLE_BID) — the engine never falls back to ltp for a limit "
    "execution."
)

CANDLE_FILL_POLICY = (
    "Candles carry interval aggregates only; fills anchor exclusively on the "
    "next record's open_price. MARKET fills at open; LIMIT fills at open iff "
    "the limit crosses open. close_price is used only for the ex-post equity "
    "mark, never for fills."
)

CANDLE_LIMIT_NO_IMPROVEMENT = (
    "Intra-bar limit touch is deliberately not modeled on candle inputs: "
    "whether a limit was touched between open and close is unknowable on "
    "interval data, and assuming it would flatter results."
)


class UnfilledReason(StrEnum):
    NO_RECORD_AFTER_DECISION = "NO_RECORD_AFTER_DECISION"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    INSUFFICIENT_POSITION = "INSUFFICIENT_POSITION"
    LIMIT_NOT_EXECUTABLE = "LIMIT_NOT_EXECUTABLE"
    NO_EXECUTABLE_ASK = "NO_EXECUTABLE_ASK"
    NO_EXECUTABLE_BID = "NO_EXECUTABLE_BID"


@dataclass(frozen=True)
class FillRecord:
    """One simulated fill: a pure function of the intent and anchor record."""

    sequence: int
    intent_index: int
    side: IntentSide
    quantity: Decimal
    anchor_price: Decimal
    slippage_per_share: Decimal
    fill_price: Decimal
    commission_amount: Decimal
    gross_value: Decimal
    cash_flow: Decimal
    record_index: int
    filled_at: datetime


@dataclass(frozen=True)
class FillOutcome:
    """One outcome per intent — 1:1 accounting, nothing is silently dropped."""

    intent_index: int
    filled: bool
    fill: FillRecord | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.filled:
            if self.fill is None:
                raise BacktestEngineError("a filled outcome requires a fill record")
            if self.reason is not None:
                raise BacktestEngineError("a filled outcome must not carry a reason")
        else:
            if self.fill is not None:
                raise BacktestEngineError("an unfilled outcome must not carry a fill record")
            if not self.reason:
                raise BacktestEngineError("an unfilled outcome requires a reason")


@dataclass(frozen=True)
class FillEvaluation:
    """Result of evaluating one intent against one anchor record."""

    outcome: FillOutcome
    fill: FillRecord | None
    cash: Decimal
    position: Decimal


def _require_decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise BacktestEngineError(f"{name} must be a Decimal")
    if not value.is_finite():
        raise BacktestEngineError(f"{name} must be finite")
    return value


def _record_timestamp(record: MarketCandle | MarketTick) -> datetime:
    if isinstance(record, MarketCandle):
        return record.candle_start
    return record.timestamp


def _unfilled(intent_index: int, reason: str, cash: Decimal, position: Decimal) -> FillEvaluation:
    outcome = FillOutcome(intent_index=intent_index, filled=False, reason=reason)
    return FillEvaluation(outcome=outcome, fill=None, cash=cash, position=position)


def evaluate_fill(
    *,
    intent: OrderIntent,
    record: MarketCandle | MarketTick,
    record_index: int,
    cash: Decimal,
    position: Decimal,
    cost_model: CostModel,
    sequence: int,
    intent_index: int,
) -> FillEvaluation:
    """Evaluate one intent against one anchor record (pure, deterministic).

    Executability is checked first (limit vs anchor, missing quote legs),
    then the long-only position check for SELL, then the cash-account
    invariant (cash never goes negative — no margin, no silent quantity
    capping). Every refusal is a data outcome with an explicit reason;
    nothing here raises except contract violations.
    """
    if not isinstance(record, (MarketCandle, MarketTick)):
        raise BacktestEngineError("record must be a MarketCandle or MarketTick")
    if not isinstance(cost_model, CostModel):
        raise BacktestEngineError("cost_model must be a CostModel")
    cash = _require_decimal(cash, "cash")
    position = _require_decimal(position, "position")
    if position < 0:
        raise BacktestEngineError("position must be non-negative")

    # --- Executability and anchor (fixed policies, never a per-call knob) ---
    if isinstance(record, MarketCandle):
        open_price = _require_decimal(record.open_price, "candle open_price")
        if intent.order_type is IntentType.LIMIT:
            if intent.limit_price is None:
                raise BacktestEngineError("limit intents require a limit_price")
            if (intent.side is IntentSide.BUY and intent.limit_price < open_price) or (
                intent.side is IntentSide.SELL and intent.limit_price > open_price
            ):
                return _unfilled(intent_index, UnfilledReason.LIMIT_NOT_EXECUTABLE.value, cash, position)
        anchor, _ = open_price, "open"
    elif intent.order_type is IntentType.LIMIT:
        if intent.side is IntentSide.BUY:
            if record.ask is None:
                return _unfilled(intent_index, UnfilledReason.NO_EXECUTABLE_ASK.value, cash, position)
            anchor = _require_decimal(record.ask, "tick ask")
            if intent.limit_price is None:
                raise BacktestEngineError("limit intents require a limit_price")
            if intent.limit_price < anchor:
                return _unfilled(intent_index, UnfilledReason.LIMIT_NOT_EXECUTABLE.value, cash, position)
        else:
            if record.bid is None:
                return _unfilled(intent_index, UnfilledReason.NO_EXECUTABLE_BID.value, cash, position)
            anchor = _require_decimal(record.bid, "tick bid")
            if intent.limit_price is None:
                raise BacktestEngineError("limit intents require a limit_price")
            if intent.limit_price > anchor:
                return _unfilled(intent_index, UnfilledReason.LIMIT_NOT_EXECUTABLE.value, cash, position)
    else:  # MARKET on ticks
        if intent.side is IntentSide.BUY:
            if record.ask is not None:
                anchor, _ = _require_decimal(record.ask, "tick ask"), "ask"
            else:
                anchor, _ = _require_decimal(record.ltp, "tick ltp"), "ltp"
        else:
            if record.bid is not None:
                anchor, _ = _require_decimal(record.bid, "tick bid"), "bid"
            else:
                anchor, _ = _require_decimal(record.ltp, "tick ltp"), "ltp"

    # A non-positive anchor is nonsense data on every path (candle open, tick
    # ask/bid, ltp fallback). Reject it loudly — model_construct smuggling of
    # zero/negative prices must never yield a silent "fill".
    if anchor <= 0:
        raise BacktestEngineError(f"anchor price must be strictly positive (got {anchor})")

    # --- Price and costs: slippage on MARKET fills only ---
    if intent.order_type is IntentType.MARKET:
        fill_price = apply_slippage(anchor, intent.side, cost_model.slippage_bps)
    else:
        fill_price = anchor
    slippage_per_share = abs(fill_price - anchor)
    commission = commission_for(cost_model.commission_per_fill)
    gross_value = intent.quantity * fill_price

    # --- Position / cash-account invariant (no margin, no negative cash) ---
    if intent.side is IntentSide.SELL:
        if position < intent.quantity:
            return _unfilled(intent_index, UnfilledReason.INSUFFICIENT_POSITION.value, cash, position)
        cash_flow = gross_value - commission
        if cash + cash_flow < 0:
            return _unfilled(intent_index, UnfilledReason.INSUFFICIENT_CASH.value, cash, position)
        new_cash = cash + cash_flow
        new_position = position - intent.quantity
    else:
        cash_flow = -(gross_value + commission)
        if cash + cash_flow < 0:
            return _unfilled(intent_index, UnfilledReason.INSUFFICIENT_CASH.value, cash, position)
        new_cash = cash + cash_flow
        new_position = position + intent.quantity

    fill = FillRecord(
        sequence=sequence,
        intent_index=intent_index,
        side=intent.side,
        quantity=intent.quantity,
        anchor_price=anchor,
        slippage_per_share=slippage_per_share,
        fill_price=fill_price,
        commission_amount=commission,
        gross_value=gross_value,
        cash_flow=cash_flow,
        record_index=record_index,
        filled_at=_record_timestamp(record),
    )
    return FillEvaluation(
        outcome=FillOutcome(intent_index=intent_index, filled=True, fill=fill),
        fill=fill,
        cash=new_cash,
        position=new_position,
    )
