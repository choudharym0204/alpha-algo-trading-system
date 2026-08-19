from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from alpha_algo_contracts import CandleTimeframe, MarketCandle, MarketTick
from alpha_algo_market_data import (
    EventKind,
    IngestStatus,
    MarketDataEngine,
    MarketDataRepository,
    RawMarketEvent,
    to_orm_candle,
    to_orm_tick,
)


def make_tick() -> MarketTick:
    now = datetime.now(UTC)
    return MarketTick(
        instrument_id=uuid4(),
        exchange="NSE",
        symbol="RELIANCE",
        timestamp=now,
        ltp=Decimal("2450.25"),
        source_broker="fake",
        source_sequence="seq-1",
        received_at=now,
    )


def make_candle() -> MarketCandle:
    now = datetime.now(UTC)
    return MarketCandle(
        instrument_id=uuid4(),
        exchange="NSE",
        symbol="RELIANCE",
        timeframe=CandleTimeframe.ONE_MINUTE,
        candle_start=now,
        open_price=Decimal("100"),
        high_price=Decimal("110"),
        low_price=Decimal("95"),
        close_price=Decimal("105"),
        source_broker="fake",
        generated_at=now,
    )


def make_tick_event(timestamp: datetime) -> RawMarketEvent:
    return RawMarketEvent(
        provider="fake",
        kind=EventKind.TICK,
        payload={
            "instrument_id": uuid4(),
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "timestamp": timestamp,
            "ltp": "2450.25",
            "source_broker": "fake",
            "source_sequence": "seq-1",
        },
        received_at=timestamp,
    )


def test_to_orm_tick_maps_fields() -> None:
    tick = make_tick()
    orm = to_orm_tick(tick)
    assert orm.symbol == "RELIANCE"
    assert orm.ltp == tick.ltp
    assert orm.source_sequence == "seq-1"
    assert orm.timestamp == tick.timestamp
    assert orm.instrument_id == tick.instrument_id


def test_to_orm_candle_maps_fields() -> None:
    candle = make_candle()
    orm = to_orm_candle(candle)
    assert orm.timeframe == "1m"
    assert orm.close_price == candle.close_price
    assert orm.candle_start == candle.candle_start
    assert orm.source_broker == candle.source_broker
    assert orm.instrument_id == candle.instrument_id


def test_engine_persists_valid_tick() -> None:
    repository = MagicMock(spec=MarketDataRepository)
    engine = MarketDataEngine(
        repository=repository,
        clock=lambda: datetime.now(UTC),
        max_age=timedelta(seconds=5),
    )
    result = engine.ingest_raw(make_tick_event(datetime.now(UTC) - timedelta(seconds=1)))
    assert result.status == IngestStatus.ACCEPTED
    repository.persist_tick.assert_called_once()
    assert engine.metrics.persisted_ticks == 1


def test_engine_rejects_invalid_before_persist() -> None:
    repository = MagicMock(spec=MarketDataRepository)
    engine = MarketDataEngine(
        repository=repository,
        clock=lambda: datetime.now(UTC),
        max_age=timedelta(seconds=5),
    )
    # zero price -> rejected during normalization, never persisted
    event = make_tick_event(datetime.now(UTC))
    event = RawMarketEvent(
        provider=event.provider,
        kind=event.kind,
        payload={**event.payload, "ltp": "0"},
        received_at=event.received_at,
    )
    result = engine.ingest_raw(event)
    assert result.status == IngestStatus.REJECTED
    repository.persist_tick.assert_not_called()


def test_database_failure_is_handled_safely() -> None:
    repository = MagicMock(spec=MarketDataRepository)
    repository.persist_tick.side_effect = RuntimeError("db down")
    engine = MarketDataEngine(
        repository=repository,
        clock=lambda: datetime.now(UTC),
        max_age=timedelta(seconds=5),
    )
    result = engine.ingest_raw(make_tick_event(datetime.now(UTC) - timedelta(seconds=1)))
    assert result.status == IngestStatus.ACCEPTED  # stream not crashed
    assert engine.metrics.persistence_failures == 1
    assert engine.metrics.persisted_ticks == 0
