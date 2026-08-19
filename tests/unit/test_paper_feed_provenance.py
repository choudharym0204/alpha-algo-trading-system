from __future__ import annotations

"""Provenance (audit trail / dedup key) tests for the paper market-data feed."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from alpha_algo_contracts import MarketTick
from alpha_algo_paper_feed import TickProvenance, provenance_of
from alpha_algo_paper_feed.errors import PaperFeedError
from alpha_algo_paper_feed.mapping import tick_to_reference

INSTRUMENT_ID = UUID("20000000-0000-0000-0000-000000000002")
TIMESTAMP = datetime(2026, 3, 1, 9, 30, 15, tzinfo=UTC)
RECEIVED_AT = datetime(2026, 3, 1, 9, 30, 15, 500000, tzinfo=UTC)


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
        received_at=RECEIVED_AT,
    )
    kwargs.update(overrides)
    return MarketTick(**kwargs)


def test_provenance_round_trip() -> None:
    provenance = provenance_of(_tick())
    assert provenance.instrument_id == INSTRUMENT_ID
    assert provenance.exchange == "NSE"
    assert provenance.symbol == "RELIANCE"
    assert provenance.source_broker == "test-broker"
    assert provenance.source_sequence == "seq-001"
    assert provenance.timestamp == TIMESTAMP
    assert provenance.received_at == RECEIVED_AT


def test_provenance_dedup_key_fields_present() -> None:
    provenance = provenance_of(_tick())
    # (source_broker, source_sequence) is the P3-003 dedup key.
    assert provenance.source_broker == "test-broker"
    assert provenance.source_sequence == "seq-001"


def test_provenance_timestamps_are_tz_aware() -> None:
    provenance = provenance_of(_tick())
    assert provenance.timestamp.utcoffset() is not None
    assert provenance.received_at.utcoffset() is not None


def test_provenance_frozen_and_immutable() -> None:
    provenance = provenance_of(_tick())
    with pytest.raises(FrozenInstanceError):
        provenance.symbol = "TATA"  # type: ignore[misc]


def test_provenance_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        TickProvenance(
            instrument_id=INSTRUMENT_ID,
            exchange="NSE",
            symbol="RELIANCE",
            source_broker="test-broker",
            source_sequence="seq-001",
            timestamp=datetime(2026, 3, 1, 9, 30, 15),  # naive
            received_at=RECEIVED_AT,
        )


def test_provenance_rejects_empty_source_fields() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        TickProvenance(
            instrument_id=INSTRUMENT_ID,
            exchange="",
            symbol="RELIANCE",
            source_broker="test-broker",
            source_sequence="seq-001",
            timestamp=TIMESTAMP,
            received_at=RECEIVED_AT,
        )


def test_provenance_rejects_non_tick_input() -> None:
    for garbage in (None, 42, "not-a-tick"):
        with pytest.raises(PaperFeedError, match="MarketTick only"):
            provenance_of(garbage)  # type: ignore[arg-type]


def test_provenance_is_deterministic() -> None:
    tick = _tick()
    assert provenance_of(tick) == provenance_of(tick)


def test_provenance_is_independent_of_conversion() -> None:
    tick = _tick()
    snapshot = tick_to_reference(tick)
    provenance = provenance_of(tick)
    # The snapshot carries no broker-origin labels; the provenance carries
    # the source identity. They never bleed into each other.
    assert not hasattr(snapshot, "source_broker")
    assert not hasattr(snapshot, "source_sequence")
    assert provenance.source_broker == "test-broker"
