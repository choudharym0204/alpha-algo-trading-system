from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_execution_engine import (
    BrokerOrderEvent,
    InvalidOrderEvent,
    InvalidOrderTransition,
    OrderEventType,
    OrderExecutionState,
    OrderLifecycle,
    OrderState,
)


NOW = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)


def _submitted_state(*, order_quantity: Decimal = Decimal("100")) -> OrderExecutionState:
    lifecycle = (
        OrderLifecycle(order_id=uuid4())
        .transition_to(
            OrderState.INTERNAL_ORDER_CREATED,
            occurred_at=NOW,
            reason="internal order created",
        )
        .transition_to(
            OrderState.SUBMISSION_REQUESTED,
            occurred_at=NOW,
            reason="risk approved submission requested",
        )
    )
    return OrderExecutionState(lifecycle=lifecycle, order_quantity=order_quantity)


def _event(
    state: OrderExecutionState,
    event_type: OrderEventType,
    *,
    fill_quantity: Decimal = Decimal("0"),
    reason: str = "broker event",
) -> BrokerOrderEvent:
    return BrokerOrderEvent(
        order_id=state.lifecycle.order_id,
        event_type=event_type,
        occurred_at=NOW,
        reason=reason,
        broker_order_id="broker-1",
        fill_quantity=fill_quantity,
    )


def test_broker_acknowledgement_does_not_mark_order_filled() -> None:
    state = _submitted_state()

    acknowledged = state.apply_event(_event(state, OrderEventType.BROKER_ACKNOWLEDGED))

    assert acknowledged.lifecycle.state == OrderState.BROKER_ACKNOWLEDGED
    assert acknowledged.filled_quantity == Decimal("0")
    assert acknowledged.lifecycle.is_terminal is False


def test_partial_fills_accumulate_without_completing_order() -> None:
    submitted = _submitted_state()
    state = submitted.apply_event(_event(submitted, OrderEventType.BROKER_ACKNOWLEDGED))

    partially_filled = state.apply_event(
        _event(state, OrderEventType.PARTIAL_FILL, fill_quantity=Decimal("25"))
    ).apply_event(_event(state, OrderEventType.PARTIAL_FILL, fill_quantity=Decimal("30")))

    assert partially_filled.lifecycle.state == OrderState.PARTIALLY_FILLED
    assert partially_filled.filled_quantity == Decimal("55")
    assert partially_filled.lifecycle.is_terminal is False


def test_final_fill_must_complete_order_exactly() -> None:
    state = _submitted_state()
    acknowledged = state.apply_event(_event(state, OrderEventType.BROKER_ACKNOWLEDGED))
    partial = acknowledged.apply_event(
        _event(acknowledged, OrderEventType.PARTIAL_FILL, fill_quantity=Decimal("25"))
    )

    filled = partial.apply_event(
        _event(partial, OrderEventType.FILL, fill_quantity=Decimal("75"))
    )

    assert filled.lifecycle.state == OrderState.FILLED
    assert filled.filled_quantity == Decimal("100")
    assert filled.lifecycle.is_terminal is True


def test_partial_fill_cannot_complete_or_overfill_order() -> None:
    state = _submitted_state(order_quantity=Decimal("10"))
    acknowledged = state.apply_event(_event(state, OrderEventType.BROKER_ACKNOWLEDGED))

    with pytest.raises(InvalidOrderEvent, match="partial fill"):
        acknowledged.apply_event(
            _event(acknowledged, OrderEventType.PARTIAL_FILL, fill_quantity=Decimal("10"))
        )


def test_fill_event_cannot_underfill_order() -> None:
    state = _submitted_state(order_quantity=Decimal("10"))
    acknowledged = state.apply_event(_event(state, OrderEventType.BROKER_ACKNOWLEDGED))

    with pytest.raises(InvalidOrderEvent, match="complete"):
        acknowledged.apply_event(
            _event(acknowledged, OrderEventType.FILL, fill_quantity=Decimal("9"))
        )


def test_rejection_and_cancellation_events_reach_terminal_states() -> None:
    rejected_state = _submitted_state()
    rejected = rejected_state.apply_event(_event(rejected_state, OrderEventType.REJECTED))

    cancel_state = _submitted_state()
    acknowledged = cancel_state.apply_event(_event(cancel_state, OrderEventType.BROKER_ACKNOWLEDGED))
    cancelled = acknowledged.apply_event(
        _event(acknowledged, OrderEventType.CANCEL_REQUESTED)
    ).apply_event(_event(acknowledged, OrderEventType.CANCELLED))

    assert rejected.lifecycle.state == OrderState.REJECTED
    assert rejected.lifecycle.is_terminal is True
    assert cancelled.lifecycle.state == OrderState.CANCELLED
    assert cancelled.lifecycle.is_terminal is True


def test_unknown_state_requires_reconciliation_before_resolution_event() -> None:
    state = _submitted_state()
    unknown = state.apply_event(_event(state, OrderEventType.UNKNOWN))

    assert unknown.lifecycle.requires_reconciliation is True

    with pytest.raises(InvalidOrderTransition):
        unknown.apply_event(_event(unknown, OrderEventType.FILL, fill_quantity=Decimal("100")))

    reconciled = unknown.apply_event(_event(unknown, OrderEventType.RECONCILIATION_REQUIRED))
    cancelled = reconciled.apply_event(_event(reconciled, OrderEventType.CANCELLED))

    assert cancelled.lifecycle.state == OrderState.CANCELLED


def test_event_order_id_must_match_execution_state() -> None:
    state = _submitted_state()
    event = BrokerOrderEvent(
        order_id=uuid4(),
        event_type=OrderEventType.BROKER_ACKNOWLEDGED,
        occurred_at=NOW,
        reason="wrong order",
    )

    with pytest.raises(InvalidOrderEvent, match="order_id"):
        state.apply_event(event)


def test_fill_events_require_positive_quantity() -> None:
    state = _submitted_state()

    with pytest.raises(ValueError, match="positive"):
        _event(state, OrderEventType.FILL, fill_quantity=Decimal("0"))


def test_order_event_applier_exposes_no_broker_submission_methods() -> None:
    state = _submitted_state()

    forbidden_names = {
        "broker",
        "broker_credentials",
        "credentials",
        "place_order",
        "submit_order",
        "send_order",
        "execute_order",
    }

    assert forbidden_names.isdisjoint(dir(state))
