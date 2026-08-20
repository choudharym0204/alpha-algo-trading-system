"""Shared helpers for Phase 16 backtesting-expansion tests.

Mirrors the in-file helpers used by the existing backtest engine tests:
explicit ``MarketTick``/``MarketCandle`` builders, an ``OrderIntent`` builder,
and a ``PortfolioInput`` assembler. No fixtures, no I/O, no randomness.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from alpha_algo_contracts import CandleTimeframe, MarketCandle, MarketTick

from alpha_algo_backtest_engine import CostModel, IntentSide, IntentType, OrderIntent
from alpha_algo_backtesting import BacktestInput

INSTRUMENT = UUID("00000000-0000-0000-0000-000000000001")
INSTRUMENT_B = UUID("00000000-0000-0000-0000-000000000002")


def utc(y: int, mo: int, d: int, h: int = 9, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def tick(
    ts: datetime,
    ltp: str,
    bid: str | None = None,
    ask: str | None = None,
    symbol: str = "TEST",
    instrument: UUID = INSTRUMENT,
) -> MarketTick:
    return MarketTick(
        instrument_id=instrument,
        exchange="NSE",
        symbol=symbol,
        timestamp=ts,
        ltp=Decimal(ltp),
        bid=Decimal(bid) if bid is not None else None,
        ask=Decimal(ask) if ask is not None else None,
        source_broker="unit",
        source_sequence=f"seq-{ts.isoformat()}-{symbol}",
        received_at=ts,
    )


def candle(
    ts: datetime,
    open_price: str,
    high: str,
    low: str,
    close: str,
    symbol: str = "TEST",
    instrument: UUID = INSTRUMENT,
    timeframe: CandleTimeframe = CandleTimeframe.ONE_DAY,
) -> MarketCandle:
    return MarketCandle(
        instrument_id=instrument,
        exchange="NSE",
        symbol=symbol,
        timeframe=timeframe,
        candle_start=ts,
        open_price=Decimal(open_price),
        high_price=Decimal(high),
        low_price=Decimal(low),
        close_price=Decimal(close),
        source_broker="unit",
        generated_at=ts,
    )


def make_input(dataset_id: str, records: tuple) -> BacktestInput:
    return BacktestInput(dataset_id=dataset_id, source="unit", records=records)


def order(
    side: IntentSide,
    order_type: IntentType,
    decided_at: datetime,
    quantity: str = "10",
    limit_price: str | None = None,
) -> OrderIntent:
    return OrderIntent(
        side=side,
        order_type=order_type,
        quantity=Decimal(quantity),
        decided_at=decided_at,
        limit_price=Decimal(limit_price) if limit_price is not None else None,
    )


def zero_cost() -> CostModel:
    return CostModel(commission_per_fill=Decimal("0"), slippage_bps=Decimal("0"))
