from __future__ import annotations

"""Conversion correctness + determinism tests for the paper market-data feed."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from alpha_algo_contracts import MarketCandle, MarketTick
from alpha_algo_paper_feed import TICK_REFERENCE_POLICY, tick_to_reference
from alpha_algo_paper_feed.errors import PaperFeedError

INSTRUMENT_ID = UUID("20000000-0000-0000-0000-000000000002")
TIMESTAMP = datetime(2026, 3, 1, 9, 30, 15, tzinfo=UTC)


def _tick(**overrides) -> MarketTick:
    kwargs = dict(
        instrument_id=INSTRUMENT_ID,
        exchange="NSE",
        symbol="RELIANCE",
        timestamp=TIMESTAMP,
        ltp=Decimal("100.00"),
        bid=Decimal("99.50"),
        ask=Decimal("100.50"),
        source_broker="test-broker",
        source_sequence="seq-001",
        received_at=TIMESTAMP,
    )
    kwargs.update(overrides)
    return MarketTick(**kwargs)


def test_full_tick_maps_all_fields() -> None:
    snapshot = tick_to_reference(_tick())
    assert snapshot.instrument_id == INSTRUMENT_ID
    assert snapshot.last == Decimal("100.00")
    assert snapshot.bid == Decimal("99.50")
    assert snapshot.ask == Decimal("100.50")
    assert snapshot.reference_at == TIMESTAMP
    for price in (snapshot.last, snapshot.bid, snapshot.ask):
        assert isinstance(price, Decimal)


def test_reference_at_never_epoch_default() -> None:
    snapshot = tick_to_reference(_tick())
    assert snapshot.reference_at != datetime(1970, 1, 1, tzinfo=UTC)
    assert snapshot.reference_at.tzinfo is not None
    assert snapshot.reference_at.utcoffset() is not None


def test_missing_quote_legs_map_to_none() -> None:
    bid_only = tick_to_reference(_tick(ask=None))
    assert bid_only.bid == Decimal("99.50")
    assert bid_only.ask is None

    ask_only = tick_to_reference(_tick(bid=None))
    assert ask_only.bid is None
    assert ask_only.ask == Decimal("100.50")

    neither = tick_to_reference(_tick(bid=None, ask=None))
    assert neither.bid is None
    assert neither.ask is None


def test_legs_never_synthesized() -> None:
    bid_only = tick_to_reference(_tick(ask=None))
    assert bid_only.ask is None  # never last, never last-derived

    ask_only = tick_to_reference(_tick(bid=None))
    assert ask_only.bid is None


def test_bid_greater_than_ask_rejected() -> None:
    incoherent = _tick(bid=Decimal("101.00"), ask=Decimal("100.00"))
    with pytest.raises(PaperFeedError, match="bid cannot exceed ask"):
        tick_to_reference(incoherent)


def test_last_outside_spread_rejected() -> None:
    outside = _tick(ltp=Decimal("150.00"))
    with pytest.raises(PaperFeedError, match="within the bid/ask spread"):
        tick_to_reference(outside)


def test_boundary_spread_equality_accepted() -> None:
    snapshot = tick_to_reference(
        _tick(ltp=Decimal("100.00"), bid=Decimal("100.00"), ask=Decimal("100.00"))
    )
    assert snapshot.last == snapshot.bid == snapshot.ask == Decimal("100.00")


def test_infinite_ltp_rejected() -> None:
    # pydantic 2.13 rejects Infinity at construction (finite_number); reachable
    # via model_construct bypass — the feed still rejects it defensively.
    bypass = MarketTick.model_construct(
        instrument_id=INSTRUMENT_ID,
        exchange="NSE",
        symbol="RELIANCE",
        timestamp=TIMESTAMP,
        ltp=Decimal("Infinity"),
        source_broker="test-broker",
        source_sequence="seq-001",
        received_at=TIMESTAMP,
    )
    with pytest.raises(PaperFeedError, match="finite"):
        tick_to_reference(bypass)


def test_infinite_bid_or_ask_rejected() -> None:
    for field in ("bid", "ask"):
        kwargs = dict(
            instrument_id=INSTRUMENT_ID,
            exchange="NSE",
            symbol="RELIANCE",
            timestamp=TIMESTAMP,
            ltp=Decimal("100.00"),
            bid=Decimal("99.50"),
            ask=Decimal("100.50"),
            source_broker="test-broker",
            source_sequence="seq-001",
            received_at=TIMESTAMP,
        )
        kwargs[field] = Decimal("Infinity")
        bypass = MarketTick.model_construct(**kwargs)
        with pytest.raises(PaperFeedError, match="finite"):
            tick_to_reference(bypass)


def test_nan_rejected() -> None:
    # NaN is rejected by the contract itself (NaN > 0 is False); reachable
    # only via model_construct bypass — the feed still rejects it defensively.
    bypass = MarketTick.model_construct(
        instrument_id=INSTRUMENT_ID,
        exchange="NSE",
        symbol="RELIANCE",
        timestamp=TIMESTAMP,
        ltp=Decimal("NaN"),
        source_broker="test-broker",
        source_sequence="seq-001",
        received_at=TIMESTAMP,
    )
    with pytest.raises(PaperFeedError, match="finite"):
        tick_to_reference(bypass)


def test_float_price_rejected() -> None:
    # Pydantic lax mode coerces float into Decimal at construction; a raw
    # float is reachable only via model_construct — the feed must reject it.
    bypass = MarketTick.model_construct(
        instrument_id=INSTRUMENT_ID,
        exchange="NSE",
        symbol="RELIANCE",
        timestamp=TIMESTAMP,
        ltp=2450.25,  # float, bypasses pydantic coercion
        bid=Decimal("99.50"),
        ask=Decimal("100.50"),
        source_broker="test-broker",
        source_sequence="seq-001",
        received_at=TIMESTAMP,
    )
    with pytest.raises(PaperFeedError, match="Decimal"):
        tick_to_reference(bypass)


def test_candle_input_rejected() -> None:
    candle = MarketCandle(
        instrument_id=INSTRUMENT_ID,
        exchange="NSE",
        symbol="RELIANCE",
        timeframe="1m",
        candle_start=TIMESTAMP,
        open_price=Decimal("100.00"),
        high_price=Decimal("101.00"),
        low_price=Decimal("99.00"),
        close_price=Decimal("100.50"),
        source_broker="test-broker",
        generated_at=TIMESTAMP,
    )
    with pytest.raises(PaperFeedError, match="MarketTick only"):
        tick_to_reference(candle)


def test_non_tick_input_rejected() -> None:
    for garbage in (None, 42, "not-a-tick"):
        with pytest.raises(PaperFeedError, match="MarketTick only"):
            tick_to_reference(garbage)  # type: ignore[arg-type]


def test_non_positive_prices_rejected() -> None:
    # Edge-case #9 (spec §4): contract rejects <= 0 at construction; the feed
    # defends the same boundary for model_construct bypasses.
    for field in ("ltp", "bid", "ask"):
        kwargs = dict(
            instrument_id=INSTRUMENT_ID,
            exchange="NSE",
            symbol="RELIANCE",
            timestamp=TIMESTAMP,
            ltp=Decimal("100.00"),
            bid=Decimal("99.50"),
            ask=Decimal("100.50"),
            source_broker="test-broker",
            source_sequence="seq-001",
            received_at=TIMESTAMP,
        )
        kwargs[field] = Decimal("0")
        bypass = MarketTick.model_construct(**kwargs)
        with pytest.raises(PaperFeedError, match="positive"):
            tick_to_reference(bypass)


def test_non_datetime_timestamp_rejected() -> None:
    bypass = MarketTick.model_construct(
        instrument_id=INSTRUMENT_ID,
        exchange="NSE",
        symbol="RELIANCE",
        timestamp="not-a-datetime",  # bypasses the pydantic validator
        ltp=Decimal("100.00"),
        bid=Decimal("99.50"),
        ask=Decimal("100.50"),
        source_broker="test-broker",
        source_sequence="seq-001",
        received_at=TIMESTAMP,
    )
    with pytest.raises(PaperFeedError, match="datetime"):
        tick_to_reference(bypass)


def test_non_uuid_instrument_id_rejected() -> None:
    bypass = MarketTick.model_construct(
        instrument_id="not-a-uuid",
        exchange="NSE",
        symbol="RELIANCE",
        timestamp=TIMESTAMP,
        ltp=Decimal("100.00"),
        bid=Decimal("99.50"),
        ask=Decimal("100.50"),
        source_broker="test-broker",
        source_sequence="seq-001",
        received_at=TIMESTAMP,
    )
    with pytest.raises(PaperFeedError, match="UUID"):
        tick_to_reference(bypass)


def test_naive_timestamp_rejected() -> None:
    bypass = MarketTick.model_construct(
        instrument_id=INSTRUMENT_ID,
        exchange="NSE",
        symbol="RELIANCE",
        timestamp=datetime(2026, 3, 1, 9, 30, 15),  # naive
        ltp=Decimal("100.00"),
        bid=Decimal("99.50"),
        ask=Decimal("100.50"),
        source_broker="test-broker",
        source_sequence="seq-001",
        received_at=TIMESTAMP,
    )
    with pytest.raises(PaperFeedError, match="timezone-aware"):
        tick_to_reference(bypass)


def test_determinism_same_tick_identical_output() -> None:
    tick = _tick()
    assert tick_to_reference(tick) == tick_to_reference(tick)


def test_conversion_has_no_state() -> None:
    tick_a = _tick(
        ltp=Decimal("101.00"),
        bid=Decimal("100.50"),
        ask=Decimal("101.50"),
        source_sequence="seq-a",
    )
    tick_b = _tick(
        ltp=Decimal("102.00"),
        bid=Decimal("101.50"),
        ask=Decimal("102.50"),
        source_sequence="seq-b",
    )
    first_a = tick_to_reference(tick_a)
    tick_to_reference(tick_b)
    assert tick_to_reference(tick_a) == first_a


def test_decimal_precision_preserved() -> None:
    precise = Decimal("2450.251234567890123")
    snapshot = tick_to_reference(
        _tick(
            ltp=precise,
            bid=Decimal("2450.250000000000000"),
            ask=Decimal("2450.260000000000000"),
        )
    )
    assert snapshot.last == precise


def test_volume_and_quantities_dropped() -> None:
    snapshot = tick_to_reference(
        _tick(
            volume=1500,
            bid_quantity=200,
            ask_quantity=300,
        )
    )
    fields = snapshot.__dataclass_fields__
    assert set(fields) == {
        "instrument_id",
        "last",
        "bid",
        "ask",
        "reference_at",
    }


def test_policy_constant_documents_mapping() -> None:
    assert "ltp->last" in TICK_REFERENCE_POLICY
    assert "timestamp->reference_at" in TICK_REFERENCE_POLICY
    assert "never synthesized" in TICK_REFERENCE_POLICY
