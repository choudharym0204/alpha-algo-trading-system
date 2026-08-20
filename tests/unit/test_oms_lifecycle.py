"""Phase 8 OMS — lifecycle/state-machine integration tests."""

from datetime import UTC, datetime

import pytest

from alpha_algo_execution_engine.lifecycle import (
    ALLOWED_TRANSITIONS,
    OrderLifecycle,
    OrderState,
)
from alpha_algo_oms.boundary import ExecutionBoundary
from alpha_algo_oms.repository import OrderRepository
from alpha_algo_oms.service import OmsService

from oms_test_support import InMemoryOmsStore, OmsSessionFactory, make_intent


def test_all_11_states_are_preserved():
    expected = {
        "INTENT_CREATED",
        "INTERNAL_ORDER_CREATED",
        "SUBMISSION_REQUESTED",
        "BROKER_ACKNOWLEDGED",
        "PARTIALLY_FILLED",
        "FILLED",
        "REJECTED",
        "CANCEL_REQUESTED",
        "CANCELLED",
        "UNKNOWN",
        "RECONCILIATION_REQUIRED",
    }
    assert {s.value for s in OrderState} == expected
    assert len(OrderState) == 11


def test_unknown_and_reconciliation_states_are_preserved():
    assert OrderState.UNKNOWN in ALLOWED_TRANSITIONS
    assert OrderState.RECONCILIATION_REQUIRED in ALLOWED_TRANSITIONS
    assert OrderState.RECONCILIATION_REQUIRED in ALLOWED_TRANSITIONS[OrderState.UNKNOWN]


def test_oms_transitions_through_the_three_states():
    store = InMemoryOmsStore()
    svc = OmsService(
        repository=OrderRepository(OmsSessionFactory(store)),
        execution_boundary=ExecutionBoundary(),
        global_halt_active=lambda: False,
    )
    result = svc.create_order(make_intent())
    # Final state is SUBMISSION_REQUESTED — never beyond the execution boundary.
    assert result.status == OrderState.SUBMISSION_REQUESTED
    # The persisted event path is exactly the three internal states.
    statuses = [e.new_status for e in store.events]
    assert statuses == [
        OrderState.INTENT_CREATED.value,
        OrderState.INTERNAL_ORDER_CREATED.value,
        OrderState.SUBMISSION_REQUESTED.value,
    ]


def test_oms_never_reaches_broker_or_filled_states():
    store = InMemoryOmsStore()
    svc = OmsService(
        repository=OrderRepository(OmsSessionFactory(store)),
        execution_boundary=ExecutionBoundary(),
        global_halt_active=lambda: False,
    )
    svc.create_order(make_intent())
    forbidden = {
        OrderState.BROKER_ACKNOWLEDGED.value,
        OrderState.FILLED.value,
        OrderState.PARTIALLY_FILLED.value,
    }
    for e in store.events:
        assert e.new_status not in forbidden


def test_invalid_transition_is_rejected_by_lifecycle():
    lifecycle = OrderLifecycle(order_id=None)  # type: ignore[arg-type]
    from alpha_algo_execution_engine.lifecycle import InvalidOrderTransition

    with pytest.raises(InvalidOrderTransition):
        # INTENT_CREATED -> FILLED is not a legal transition
        lifecycle.transition_to(
            OrderState.FILLED, occurred_at=datetime.now(UTC), reason="forged"
        )


def test_terminal_states_have_no_outgoing_transitions():
    for terminal in (OrderState.FILLED, OrderState.REJECTED, OrderState.CANCELLED):
        assert ALLOWED_TRANSITIONS[terminal] == frozenset()


def test_submission_can_go_to_rejected_or_acknowledged_or_unknown():
    targets = ALLOWED_TRANSITIONS[OrderState.SUBMISSION_REQUESTED]
    assert OrderState.BROKER_ACKNOWLEDGED in targets
    assert OrderState.REJECTED in targets
    assert OrderState.UNKNOWN in targets
    assert OrderState.CANCEL_REQUESTED in targets
