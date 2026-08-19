from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from alpha_algo_contracts import CandleTimeframe, MarketCandle, MarketTick


def test_market_tick_accepts_canonical_fields() -> None:
    now = datetime.now(UTC)

    tick = MarketTick(
        instrument_id=uuid4(),
        exchange="NSE",
        symbol="RELIANCE",
        timestamp=now,
        ltp=Decimal("2450.25"),
        volume=100,
        bid=Decimal("2450.20"),
        ask=Decimal("2450.30"),
        bid_quantity=50,
        ask_quantity=40,
        source_broker="example",
        source_sequence="seq-1",
        received_at=now,
    )

    assert tick.ltp == Decimal("2450.25")
    assert tick.source_sequence == "seq-1"


def test_market_tick_rejects_invalid_price_and_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        MarketTick(
            instrument_id=uuid4(),
            exchange="NSE",
            symbol="RELIANCE",
            timestamp=datetime.now(),
            ltp=Decimal("0"),
            source_broker="example",
            source_sequence="seq-1",
            received_at=datetime.now(),
        )


def test_market_candle_validates_price_range() -> None:
    now = datetime.now(UTC)

    with pytest.raises(ValidationError):
        MarketCandle(
            instrument_id=uuid4(),
            exchange="NSE",
            symbol="RELIANCE",
            timeframe=CandleTimeframe.ONE_MINUTE,
            candle_start=now,
            open_price=Decimal("100"),
            high_price=Decimal("90"),
            low_price=Decimal("95"),
            close_price=Decimal("98"),
            source_broker="example",
            generated_at=now,
        )


def test_market_candle_accepts_valid_ohlc() -> None:
    now = datetime.now(UTC)

    candle = MarketCandle(
        instrument_id=uuid4(),
        exchange="NSE",
        symbol="RELIANCE",
        timeframe=CandleTimeframe.FIVE_MINUTES,
        candle_start=now,
        open_price=Decimal("100"),
        high_price=Decimal("110"),
        low_price=Decimal("95"),
        close_price=Decimal("105"),
        volume=500,
        source_broker="example",
        generated_at=now,
    )

    assert candle.timeframe == CandleTimeframe.FIVE_MINUTES
    assert candle.low_price <= candle.close_price <= candle.high_price

