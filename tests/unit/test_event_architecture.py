"""Unit tests for the unified domain-event contract + in-process event bus."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from alpha_algo_contracts import (
    DomainEvent,
    DomainEventError,
    EventType,
    create_event,
)
from alpha_algo_event_bus import EventBus, NoopEventBus


# --------------------------------------------------------------------------- #
# DomainEvent envelope
# --------------------------------------------------------------------------- #

def test_create_event_is_valid_and_tz_aware() -> None:
    event = create_event(
        event_type=EventType.ORDER_CREATED,
        source="alpha-algo-oms",
        payload={"order_id": "o1"},
    )
    assert event.event_type == "order.created"
    assert event.occurred_at.tzinfo is not None
    assert event.event_id


def test_event_type_must_be_safe_pattern() -> None:
    with pytest.raises(DomainEventError):
        create_event(event_type="Bad Type!", source="s")
    with pytest.raises(DomainEventError):
        create_event(event_type="UPPER.case", source="s")
    with pytest.raises(DomainEventError):
        create_event(event_type="", source="s")


def test_occurred_at_must_be_timezone_aware() -> None:
    naive = datetime(2026, 8, 21, 10, 0, 0)
    with pytest.raises(DomainEventError):
        create_event(event_type="system.health", source="s", occurred_at=naive)


def test_source_must_be_non_empty() -> None:
    with pytest.raises(DomainEventError):
        create_event(event_type="system.health", source="   ")


def test_payload_must_be_dict() -> None:
    with pytest.raises(DomainEventError):
        DomainEvent(
            event_type="system.health",
            occurred_at=datetime.now(timezone.utc),
            source="s",
            payload="not-a-dict",  # type: ignore[arg-type]
        )


def test_no_self_causation() -> None:
    e = create_event(event_type="system.health", source="s")
    with pytest.raises(DomainEventError):
        DomainEvent(
            event_type="system.health",
            occurred_at=datetime.now(timezone.utc),
            source="s",
            causation_id=str(e.event_id),
            event_id=e.event_id,
        )


def test_validate_no_secrets_rejects_sensitive_keys() -> None:
    with pytest.raises(DomainEventError):
        create_event(event_type="system.health", source="s", payload={"password": "x"})
    with pytest.raises(DomainEventError):
        create_event(event_type="system.health", source="s", payload={"access_token": "x"})
    with pytest.raises(DomainEventError):
        create_event(
            event_type="system.health",
            source="s",
            payload={"nested": {"api_key": "x"}},
        )


def test_validate_no_secrets_allows_legit_keys() -> None:
    # "identity_key" / "order_id" are not sensitive (no token/secret/api_key).
    create_event(
        event_type="order.created",
        source="oms",
        payload={"identity_key": "k", "order_id": "o1"},
    )


def test_derive_links_causation_and_preserves_correlation() -> None:
    parent = create_event(
        event_type=EventType.SIGNAL_ACCEPTED,
        source="signal-engine",
        correlation_id="corr-1",
        trace_id="trace-1",
        domain_ids={"signal_id": "s1"},
    )
    child = parent.derive(
        event_type=EventType.RISK_DECISION,
        payload={"decision": "APPROVED"},
    )
    assert child.causation_id == str(parent.event_id)
    assert child.correlation_id == "corr-1"
    assert child.trace_id == "trace-1"
    assert child.domain_ids["signal_id"] == "s1"
    assert child.event_type == "risk.decision"


def test_to_dict_round_trip() -> None:
    event = create_event(
        event_type=EventType.ORDER_CREATED,
        source="oms",
        payload={"order_id": "o1"},
        domain_ids={"order_id": "o1"},
    )
    d = event.to_dict()
    assert d["event_type"] == "order.created"
    assert d["domain_ids"] == {"order_id": "o1"}
    assert d["payload"] == {"order_id": "o1"}


# --------------------------------------------------------------------------- #
# EventBus
# --------------------------------------------------------------------------- #

def test_publish_delivers_to_subscriber() -> None:
    bus = EventBus()
    received: list[DomainEvent] = []
    bus.subscribe(EventType.ORDER_CREATED, received.append)
    event = create_event(event_type=EventType.ORDER_CREATED, source="oms")
    assert bus.publish(event) == 1
    assert received == [event]


def test_exact_and_wildcard_both_receive() -> None:
    bus = EventBus()
    exact: list[DomainEvent] = []
    wildcard: list[DomainEvent] = []
    bus.subscribe(EventType.ORDER_CREATED, exact.append)
    bus.subscribe("*", wildcard.append)
    event = create_event(event_type=EventType.ORDER_CREATED, source="oms")
    assert bus.publish(event) == 2
    assert len(exact) == 1
    assert len(wildcard) == 1


def test_publish_many_is_fifo() -> None:
    bus = EventBus()
    seen: list[str] = []
    bus.subscribe("*", lambda e: seen.append(e.event_type))
    bus.publish_many(
        [
            create_event(event_type="a.start", source="s"),
            create_event(event_type="b.mid", source="s"),
            create_event(event_type="c.end", source="s"),
        ]
    )
    assert seen == ["a.start", "b.mid", "c.end"]


def test_handler_failure_is_isolated() -> None:
    bus = EventBus()
    good: list[DomainEvent] = []

    def bad_handler(_event: DomainEvent) -> None:
        raise RuntimeError("boom")

    bus.subscribe(EventType.ORDER_CREATED, bad_handler)
    bus.subscribe(EventType.ORDER_CREATED, good.append)
    event = create_event(event_type=EventType.ORDER_CREATED, source="oms")

    # Publisher is not broken by the failing handler.
    assert bus.publish(event) == 2
    assert good == [event]
    failures = bus.failures()
    assert len(failures) == 1
    assert failures[0].event_type == "order.created"
    assert "boom" in failures[0].to_dict()["error"]


def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    received: list[DomainEvent] = []
    sub = bus.subscribe(EventType.ORDER_CREATED, received.append)
    event1 = create_event(event_type=EventType.ORDER_CREATED, source="oms")
    bus.publish(event1)
    sub.cancel()
    event2 = create_event(event_type=EventType.ORDER_CREATED, source="oms")
    bus.publish(event2)
    assert received == [event1]
    assert bus.handler_count(EventType.ORDER_CREATED) == 0


def test_publish_rejects_non_event() -> None:
    bus = EventBus()
    with pytest.raises(TypeError):
        bus.publish("not an event")  # type: ignore[arg-type]


def test_published_count_tracks() -> None:
    bus = EventBus()
    bus.publish(create_event(event_type="system.health", source="s"))
    bus.publish(create_event(event_type="system.health", source="s"))
    assert bus.published_count() == 2


def test_noop_bus_delivers_nothing() -> None:
    bus = NoopEventBus()
    received: list[DomainEvent] = []
    bus.subscribe("*", received.append)
    assert bus.publish(create_event(event_type="system.health", source="s")) == 0
    assert received == []
    assert bus.handler_count() == 0
