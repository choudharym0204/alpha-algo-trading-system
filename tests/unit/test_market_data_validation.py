from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alpha_algo_market_data import (
    EventKind,
    IngestStatus,
    MarketDataEngine,
    RawMarketEvent,
)


def make_tick_event(
    *,
    timestamp: datetime,
    source_sequence: str = "seq-1",
    symbol: str = "RELIANCE",
    ltp: object = "2450.25",
    extra: dict | None = None,
) -> RawMarketEvent:
    payload = {
        "instrument_id": uuid4(),
        "exchange": "NSE",
        "symbol": symbol,
        "timestamp": timestamp,
        "ltp": ltp,
        "volume": 100,
        "bid": "2450.20",
        "ask": "2450.30",
        "bid_quantity": 50,
        "ask_quantity": 40,
        "source_broker": "fake",
        "source_sequence": source_sequence,
    }
    if extra:
        payload.update(extra)
    return RawMarketEvent(
        provider="fake",
        kind=EventKind.TICK,
        payload=payload,
        received_at=timestamp,
    )


def _engine(**kwargs) -> MarketDataEngine:
    now = datetime.now(UTC)
    return MarketDataEngine(
        clock=lambda: now,
        max_age=timedelta(seconds=5),
        **kwargs,
    )


def test_valid_tick_is_accepted() -> None:
    now = datetime.now(UTC)
    engine = _engine()
    result = engine.ingest_raw(make_tick_event(timestamp=now - timedelta(seconds=1)))
    assert result.status == IngestStatus.ACCEPTED
    assert result.tick is not None
    assert result.tick.ltp == Decimal("2450.25")


def test_zero_price_tick_is_rejected() -> None:
    engine = _engine()
    result = engine.ingest_raw(
        make_tick_event(timestamp=datetime.now(UTC), ltp="0")
    )
    assert result.status == IngestStatus.REJECTED


def test_negative_price_tick_is_rejected() -> None:
    engine = _engine()
    result = engine.ingest_raw(
        make_tick_event(timestamp=datetime.now(UTC), ltp="-5.0")
    )
    assert result.status == IngestStatus.REJECTED


def test_naive_timestamp_is_rejected() -> None:
    engine = _engine()
    result = engine.ingest_raw(
        make_tick_event(timestamp=datetime.now(), ltp="2450.25")
    )
    assert result.status == IngestStatus.REJECTED


def test_future_timestamp_is_rejected() -> None:
    now = datetime.now(UTC)
    engine = _engine()
    result = engine.ingest_raw(
        make_tick_event(timestamp=now + timedelta(seconds=10))
    )
    assert result.status == IngestStatus.FUTURE


def test_stale_tick_is_rejected() -> None:
    now = datetime.now(UTC)
    engine = _engine()
    result = engine.ingest_raw(
        make_tick_event(timestamp=now - timedelta(seconds=10))
    )
    assert result.status == IngestStatus.STALE


def test_duplicate_tick_is_rejected() -> None:
    now = datetime.now(UTC)
    engine = _engine()
    event = make_tick_event(timestamp=now - timedelta(seconds=1))
    assert engine.ingest_raw(event).status == IngestStatus.ACCEPTED
    assert engine.ingest_raw(event).status == IngestStatus.DUPLICATE


def test_malformed_payload_is_rejected() -> None:
    engine = _engine()
    event = RawMarketEvent(
        provider="fake",
        kind=EventKind.TICK,
        payload={"symbol": "RELIANCE"},  # missing required keys
        received_at=datetime.now(UTC),
    )
    result = engine.ingest_raw(event)
    assert result.status == IngestStatus.REJECTED
    assert "malformed" in result.reason


def test_unsupported_instrument_is_rejected() -> None:
    now = datetime.now(UTC)
    engine = _engine(allowed_symbols={"INFY"})
    result = engine.ingest_raw(
        make_tick_event(timestamp=now - timedelta(seconds=1), symbol="RELIANCE")
    )
    assert result.status == IngestStatus.REJECTED
    assert result.reason == "unsupported_instrument"


def test_infinite_price_tick_is_rejected() -> None:
    engine = _engine()
    result = engine.ingest_raw(
        make_tick_event(timestamp=datetime.now(UTC), ltp="inf")
    )
    assert result.status == IngestStatus.REJECTED


def test_nan_price_tick_is_rejected() -> None:
    engine = _engine()
    result = engine.ingest_raw(
        make_tick_event(timestamp=datetime.now(UTC), ltp="nan")
    )
    assert result.status == IngestStatus.REJECTED


def test_invalid_timeframe_candle_is_rejected() -> None:
    engine = _engine()
    now = datetime.now(UTC)
    event = RawMarketEvent(
        provider="fake",
        kind=EventKind.CANDLE,
        payload={
            "instrument_id": uuid4(),
            "exchange": "NSE",
            "symbol": "RELIANCE",
            "timeframe": "banana",
            "candle_start": now - timedelta(seconds=1),
            "open_price": "100",
            "high_price": "110",
            "low_price": "95",
            "close_price": "105",
            "source_broker": "fake",
            "generated_at": now,
        },
        received_at=now,
    )
    result = engine.ingest_raw(event)
    assert result.status == IngestStatus.REJECTED


def test_consumer_exception_is_isolated() -> None:
    engine = _engine()
    received: list = []

    def bad_consumer(tick) -> None:
        raise RuntimeError("boom")

    engine.add_tick_consumer(bad_consumer)
    engine.add_tick_consumer(received.append)
    now = datetime.now(UTC)
    result = engine.ingest_raw(make_tick_event(timestamp=now - timedelta(seconds=1)))
    assert result.status == IngestStatus.ACCEPTED
    assert len(received) == 1
    assert engine.metrics.consumer_failures == 1
