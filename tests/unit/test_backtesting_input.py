from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from alpha_algo_backtesting import canonical_serialize, content_sha256
from alpha_algo_contracts import CandleTimeframe, MarketCandle

INSTRUMENT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _candle(
    close: str,
    minute: int,
    *,
    open_price: str = "100.00",
    exchange: str = "TESTEX",
    symbol: str = "TEST.NS",
    timeframe: CandleTimeframe = CandleTimeframe.ONE_MINUTE,
    start_year: int = 2026,
) -> MarketCandle:
    start = datetime(start_year, 1, 2, 9, minute, tzinfo=UTC)
    price = Decimal(close)
    return MarketCandle(
        instrument_id=INSTRUMENT_ID,
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        candle_start=start,
        open_price=Decimal(open_price),
        high_price=max(price, Decimal(open_price)),
        low_price=min(price, Decimal(open_price)),
        close_price=price,
        volume=100,
        source_broker="test-source",
        generated_at=start,
    )


def _records(n: int) -> tuple[MarketCandle, ...]:
    return tuple(_candle(str(100 + minute), minute) for minute in range(n))


def _input(records: tuple[MarketCandle, ...] | None = None) -> object:
    from alpha_algo_backtesting import BacktestInput

    return BacktestInput(
        dataset_id="ds-001",
        source="synthetic_test_fixture",
        records=records if records is not None else _records(3),
    )


def test_input_requires_explicit_records() -> None:
    from alpha_algo_backtesting import BacktestInput

    with pytest.raises(ValueError, match="backtest requires at least one data record"):
        BacktestInput(dataset_id="ds-001", source="synthetic_test_fixture", records=())


def test_input_rejects_unsorted_records() -> None:
    records = (_candle("101.00", 3), _candle("102.00", 1))

    with pytest.raises(ValueError, match="sorted ascending"):
        _input(records)


def test_input_rejects_duplicate_timestamps() -> None:
    records = (_candle("101.00", 1), _candle("102.00", 1))

    with pytest.raises(ValueError, match="duplicate record timestamp"):
        _input(records)


def test_input_rejects_mixed_record_kinds() -> None:
    from alpha_algo_backtesting import BacktestInput
    from alpha_algo_contracts import MarketTick

    candles = _records(1)
    tick = MarketTick(
        instrument_id=INSTRUMENT_ID,
        exchange="TESTEX",
        symbol="TEST.NS",
        timestamp=datetime(2026, 1, 2, 9, 2, tzinfo=UTC),
        ltp=Decimal("101.00"),
        bid=Decimal("100.90"),
        ask=Decimal("101.10"),
        source_broker="test-source",
        source_sequence="1",
        received_at=datetime(2026, 1, 2, 9, 2, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="same kind"):
        BacktestInput(dataset_id="ds-001", source="synthetic_test_fixture", records=(*candles, tick))


def test_input_rejects_incoherent_series() -> None:
    records = list(_records(2))
    other = _candle("103.00", 2)
    records.append(
        MarketCandle(
            instrument_id=UUID("00000000-0000-0000-0000-000000000099"),
            exchange=other.exchange,
            symbol=other.symbol,
            timeframe=other.timeframe,
            candle_start=other.candle_start,
            open_price=other.open_price,
            high_price=other.high_price,
            low_price=other.low_price,
            close_price=other.close_price,
            volume=other.volume,
            source_broker=other.source_broker,
            generated_at=other.generated_at,
        )
    )

    with pytest.raises(ValueError, match="single instrument"):
        _input(tuple(records))


def test_input_rejects_mixed_exchange() -> None:
    records = list(_records(2))
    records.append(_candle("103.00", 2, exchange="OTHER"))

    with pytest.raises(ValueError, match="single exchange"):
        _input(tuple(records))


def test_input_rejects_mixed_symbol() -> None:
    records = list(_records(2))
    records.append(_candle("103.00", 2, symbol="OTHER.NS"))

    with pytest.raises(ValueError, match="single symbol"):
        _input(tuple(records))


def test_input_rejects_mixed_timeframe() -> None:
    records = list(_records(2))
    records.append(_candle("103.00", 2, timeframe=CandleTimeframe.FIVE_MINUTES))

    with pytest.raises(ValueError, match="single timeframe"):
        _input(tuple(records))


def test_input_rejects_tick_with_bid_above_ask() -> None:
    from alpha_algo_backtesting import BacktestInput
    from alpha_algo_contracts import MarketTick

    tick = MarketTick(
        instrument_id=INSTRUMENT_ID,
        exchange="TESTEX",
        symbol="TEST.NS",
        timestamp=datetime(2026, 1, 2, 9, 1, tzinfo=UTC),
        ltp=Decimal("101.00"),
        bid=Decimal("101.50"),
        ask=Decimal("101.00"),
        source_broker="test-source",
        source_sequence="1",
        received_at=datetime(2026, 1, 2, 9, 1, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="bid cannot exceed ask"):
        BacktestInput(dataset_id="ds-001", source="synthetic_test_fixture", records=(tick,))


def test_input_exposes_deterministic_summary() -> None:
    data = _input()

    assert data.record_count == 3
    assert data.records_kind == "candles"
    assert data.first_timestamp == datetime(2026, 1, 2, 9, 0, tzinfo=UTC)
    assert data.last_timestamp == datetime(2026, 1, 2, 9, 2, tzinfo=UTC)
    assert data.symbol_counts == (("TEST.NS", 3),)
    assert len(data.content_sha256) == 64


def test_manifest_is_stable_and_content_bound() -> None:
    first = _input(_records(3))
    second = _input(_records(3))

    assert first.content_sha256 == second.content_sha256

    tampered = list(_records(3))
    tampered[-1] = _candle("999.00", 2)
    assert _input(tuple(tampered)).content_sha256 != first.content_sha256


def test_manifest_is_independent_of_metadata_and_datasets() -> None:
    from alpha_algo_backtesting import BacktestInput

    a = BacktestInput(dataset_id="ds-a", source="synthetic_test_fixture", records=_records(3), metadata={"note": "x"})
    b = BacktestInput(dataset_id="ds-b", source="synthetic_test_fixture", records=_records(3), metadata={"note": "y"})

    # Dataset identity and caller metadata are provenance, not content.
    assert a.content_sha256 == b.content_sha256


def test_canonical_serialize_is_platform_stable() -> None:
    candle = _candle("101.00", 1)

    serialized = canonical_serialize(candle)

    assert serialized == canonical_serialize(candle)
    assert "TEST.NS" in serialized
    assert "+00:00" in serialized
    assert isinstance(content_sha256((candle,)), str)


def test_canonical_serialize_handles_ticks() -> None:
    from alpha_algo_contracts import MarketTick

    tick = MarketTick(
        instrument_id=INSTRUMENT_ID,
        exchange="TESTEX",
        symbol="TEST.NS",
        timestamp=datetime(2026, 1, 2, 9, 1, tzinfo=UTC),
        ltp=Decimal("101.00"),
        bid=Decimal("100.90"),
        ask=Decimal("101.10"),
        bid_quantity=10,
        ask_quantity=20,
        source_broker="test-source",
        source_sequence="42",
        received_at=datetime(2026, 1, 2, 9, 1, tzinfo=UTC),
    )

    serialized = canonical_serialize(tick)

    assert "test-source" in serialized
    assert "42" in serialized
    assert serialized == canonical_serialize(tick)
    assert len(content_sha256((tick,))) == 64


def test_manifest_is_representation_precise_for_decimals() -> None:
    # Documented behavior: content identity is representation-precise, so
    # trailing-zero price representations are distinct content.
    padded = _candle("100.50", 1)
    unpadded = _candle("100.5", 1)

    assert padded.close_price == unpadded.close_price  # numerically equal
    assert content_sha256((padded,)) != content_sha256((unpadded,))


def test_naive_timestamp_records_are_rejected_by_the_contract() -> None:
    # Defense in depth: the shared contract rejects naive timestamps before
    # BacktestInput validation can ever see them.
    with pytest.raises(Exception, match="timezone-aware"):
        MarketCandle(
            instrument_id=INSTRUMENT_ID,
            exchange="TESTEX",
            symbol="TEST.NS",
            timeframe=CandleTimeframe.ONE_MINUTE,
            candle_start=datetime(2026, 1, 2, 9, 1),  # naive
            open_price=Decimal("100.00"),
            high_price=Decimal("101.00"),
            low_price=Decimal("99.00"),
            close_price=Decimal("100.50"),
            volume=100,
            source_broker="test-source",
            generated_at=datetime(2026, 1, 2, 9, 1),  # naive
        )


def test_future_timestamps_are_accepted_as_explicit_history() -> None:
    # Documented policy: no wall-clock recency check; inputs are treated as
    # explicit history exactly as given.
    records = tuple(_candle("101.00", minute, start_year=2099) for minute in (0, 1))

    data = _input(records)

    assert data.first_timestamp.year == 2099
    assert data.last_timestamp.year == 2099
