"""Phase 10 — broker event normalization + deduplication tests."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_broker_integration.events import (
    BrokerEventType,
    DuplicateEventError,
    EventDeduplicator,
    NormalizedBrokerEvent,
    compute_event_identity,
)


def _event(**overrides) -> NormalizedBrokerEvent:
    kwargs = dict(
        order_id=uuid4(),
        event_type=BrokerEventType.FILL,
        broker_order_id="broker-1",
        fill_quantity=Decimal("10"),
        occurred_at=datetime.now(UTC),
        reason="fill",
        source_event_id="evt-1",
    )
    kwargs.update(overrides)
    return NormalizedBrokerEvent(**kwargs)


def test_event_identity_prefers_source_id():
    oid = uuid4()
    e1 = _event(order_id=oid, source_event_id="evt-1")
    e2 = _event(order_id=oid, source_event_id="evt-1")
    assert compute_event_identity(e1) == compute_event_identity(e2)


def test_event_identity_is_deterministic():
    e = _event(source_event_id=None)
    assert compute_event_identity(e) == compute_event_identity(e)


def test_deduplicator_accepts_new_event():
    d = EventDeduplicator()
    assert d.apply(_event()) is True


def test_deduplicator_drops_exact_duplicate():
    d = EventDeduplicator()
    event = _event()
    assert d.apply(event) is True
    assert d.apply(event) is False  # exact duplicate -> no effect


def test_deduplicator_rejects_conflicting_reuse():
    d = EventDeduplicator()
    oid = uuid4()
    e1 = _event(order_id=oid, fill_quantity=Decimal("10"), source_event_id="evt-1")
    e2 = _event(order_id=oid, fill_quantity=Decimal("99"), source_event_id="evt-1")
    d.apply(e1)
    with pytest.raises(DuplicateEventError):
        d.apply(e2)  # same identity, different payload -> conflict


def test_event_content_difference_detected():
    # two events with the same source id but different payload must conflict
    oid = uuid4()
    e1 = _event(order_id=oid, reason="a", source_event_id="same")
    e2 = _event(order_id=oid, reason="b", source_event_id="same")
    d = EventDeduplicator()
    d.apply(e1)
    with pytest.raises(DuplicateEventError):
        d.apply(e2)
