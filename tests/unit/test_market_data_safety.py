from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_contracts import MarketTick
from alpha_algo_market_data import DuplicateTickDetector, evaluate_staleness


def make_tick(*, timestamp: datetime, source_sequence: str = "seq-1") -> MarketTick:
    return MarketTick(
        instrument_id=uuid4(),
        exchange="NSE",
        symbol="RELIANCE",
        timestamp=timestamp,
        ltp=Decimal("2450.25"),
        source_broker="example",
        source_sequence=source_sequence,
        received_at=timestamp,
    )


def test_stale_data_decision_marks_fresh_tick() -> None:
    now = datetime.now(UTC)
    tick = make_tick(timestamp=now - timedelta(seconds=2))

    decision = evaluate_staleness(tick, now=now, max_age=timedelta(seconds=5))

    assert decision.is_stale is False
    assert decision.reason == "tick_timestamp_fresh"


def test_stale_data_decision_marks_old_tick() -> None:
    now = datetime.now(UTC)
    tick = make_tick(timestamp=now - timedelta(seconds=10))

    decision = evaluate_staleness(tick, now=now, max_age=timedelta(seconds=5))

    assert decision.is_stale is True
    assert decision.reason == "tick_timestamp_stale"


def test_stale_data_decision_rejects_naive_now() -> None:
    tick = make_tick(timestamp=datetime.now(UTC))

    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_staleness(tick, now=datetime.now(), max_age=timedelta(seconds=5))


def test_duplicate_tick_detector_tracks_broker_sequence() -> None:
    detector = DuplicateTickDetector()
    now = datetime.now(UTC)

    first = make_tick(timestamp=now, source_sequence="seq-1")
    duplicate = make_tick(timestamp=now, source_sequence="seq-1")
    second = make_tick(timestamp=now, source_sequence="seq-2")

    assert detector.is_duplicate(first) is False
    assert detector.is_duplicate(duplicate) is True
    assert detector.is_duplicate(second) is False


def test_duplicate_tick_detector_is_bounded() -> None:
    detector = DuplicateTickDetector(maxsize=3)
    now = datetime.now(UTC)

    # fill beyond capacity: the oldest key must be evicted
    detector.is_duplicate(make_tick(timestamp=now, source_sequence="seq-1"))
    detector.is_duplicate(make_tick(timestamp=now, source_sequence="seq-2"))
    detector.is_duplicate(make_tick(timestamp=now, source_sequence="seq-3"))
    detector.is_duplicate(make_tick(timestamp=now, source_sequence="seq-4"))

    assert len(detector) == 3
    # seq-1 was evicted, so it is no longer considered a duplicate
    assert detector.is_duplicate(make_tick(timestamp=now, source_sequence="seq-1")) is False
    # seq-4 (most recent) is still tracked
    assert detector.is_duplicate(make_tick(timestamp=now, source_sequence="seq-4")) is True


def test_duplicate_tick_detector_rejects_bad_maxsize() -> None:
    with pytest.raises(ValueError):
        DuplicateTickDetector(maxsize=0)

