from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from alpha_algo_execution_engine import (
    InvalidOrderTransition,
    OrderLifecycle,
    OrderState,
    OrderStateTransition,
)


NOW = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)


def _advance(lifecycle: OrderLifecycle, *states: OrderState) -> OrderLifecycle:
    current = lifecycle
    for state in states:
        current = current.transition_to(state, occurred_at=NOW, reason=f"to {state}")
    return current


def test_order_lifecycle_starts_at_intent_created() -> None:
    lifecycle = OrderLifecycle(order_id=uuid4())

    assert lifecycle.state == OrderState.INTENT_CREATED
    assert lifecycle.transitions == ()
    assert lifecycle.is_terminal is False


def test_order_lifecycle_follows_valid_submission_path_without_fill_assumption() -> None:
    lifecycle = _advance(
        OrderLifecycle(order_id=uuid4()),
        OrderState.INTERNAL_ORDER_CREATED,
        OrderState.SUBMISSION_REQUESTED,
        OrderState.BROKER_ACKNOWLEDGED,
    )

    assert lifecycle.state == OrderState.BROKER_ACKNOWLEDGED
    assert lifecycle.is_terminal is False
    assert [transition.to_state for transition in lifecycle.transitions] == [
        OrderState.INTERNAL_ORDER_CREATED,
        OrderState.SUBMISSION_REQUESTED,
        OrderState.BROKER_ACKNOWLEDGED,
    ]


def test_submitted_order_cannot_skip_directly_to_filled() -> None:
    lifecycle = _advance(
        OrderLifecycle(order_id=uuid4()),
        OrderState.INTERNAL_ORDER_CREATED,
        OrderState.SUBMISSION_REQUESTED,
    )

    with pytest.raises(InvalidOrderTransition):
        lifecycle.transition_to(OrderState.FILLED, occurred_at=NOW, reason="broker fill")


def test_partial_fill_is_first_class_and_can_be_completed() -> None:
    lifecycle = _advance(
        OrderLifecycle(order_id=uuid4()),
        OrderState.INTERNAL_ORDER_CREATED,
        OrderState.SUBMISSION_REQUESTED,
        OrderState.BROKER_ACKNOWLEDGED,
        OrderState.PARTIALLY_FILLED,
        OrderState.PARTIALLY_FILLED,
        OrderState.FILLED,
    )

    assert lifecycle.state == OrderState.FILLED
    assert lifecycle.is_terminal is True


def test_rejected_and_cancelled_orders_are_terminal() -> None:
    rejected = _advance(
        OrderLifecycle(order_id=uuid4()),
        OrderState.INTERNAL_ORDER_CREATED,
        OrderState.REJECTED,
    )
    cancelled = _advance(
        OrderLifecycle(order_id=uuid4()),
        OrderState.INTERNAL_ORDER_CREATED,
        OrderState.SUBMISSION_REQUESTED,
        OrderState.BROKER_ACKNOWLEDGED,
        OrderState.CANCEL_REQUESTED,
        OrderState.CANCELLED,
    )

    assert rejected.is_terminal is True
    assert cancelled.is_terminal is True

    with pytest.raises(InvalidOrderTransition):
        rejected.transition_to(OrderState.SUBMISSION_REQUESTED, occurred_at=NOW, reason="retry")


def test_unknown_state_requires_reconciliation_before_resolution() -> None:
    lifecycle = _advance(
        OrderLifecycle(order_id=uuid4()),
        OrderState.INTERNAL_ORDER_CREATED,
        OrderState.SUBMISSION_REQUESTED,
        OrderState.UNKNOWN,
    )

    assert lifecycle.requires_reconciliation is True

    with pytest.raises(InvalidOrderTransition):
        lifecycle.transition_to(OrderState.FILLED, occurred_at=NOW, reason="optimistic fill")

    reconciled = lifecycle.transition_to(
        OrderState.RECONCILIATION_REQUIRED,
        occurred_at=NOW,
        reason="broker state unknown",
    ).transition_to(OrderState.CANCELLED, occurred_at=NOW, reason="broker reports cancelled")

    assert reconciled.state == OrderState.CANCELLED


def test_order_transition_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        OrderStateTransition(
            from_state=OrderState.INTENT_CREATED,
            to_state=OrderState.INTERNAL_ORDER_CREATED,
            occurred_at=datetime(2026, 1, 1),
            reason="created",
        )


def test_order_lifecycle_exposes_no_broker_submission_methods() -> None:
    lifecycle = OrderLifecycle(order_id=uuid4())

    forbidden_names = {
        "broker",
        "broker_credentials",
        "credentials",
        "place_order",
        "submit_order",
        "send_order",
        "execute_order",
    }

    assert forbidden_names.isdisjoint(dir(lifecycle))
