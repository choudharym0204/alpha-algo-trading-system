"""Phase 8 OMS — service golden-flow, idempotency, conflict, cancel tests."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from alpha_algo_execution_engine.lifecycle import OrderState
from alpha_algo_oms.boundary import ExecutionBoundary
from alpha_algo_oms.errors import (
    IntentConflictError,
    InvalidStateTransitionError,
    OrderNotFoundError,
    PersistenceError,
    RiskApprovalError,
    TradingModeError,
)
from alpha_algo_oms.repository import OrderRepository
from alpha_algo_oms.service import OmsService

from oms_test_support import (
    InMemoryOmsStore,
    OmsSessionFactory,
    expired_intent,
    make_intent,
)


class RecordingPort:
    def __init__(self):
        self.handoffs = []

    def submit(self, handoff):
        self.handoffs.append(handoff)


def make_service(store=None, *, halt=False, fail_commit=None):
    store = store or InMemoryOmsStore()
    repo = OrderRepository(OmsSessionFactory(store, fail_commit=fail_commit))
    port = RecordingPort()
    svc = OmsService(
        repository=repo,
        execution_boundary=ExecutionBoundary(port=port),
        global_halt_active=lambda: halt,
    )
    return svc, store, port


def test_golden_flow_reaches_submission_requested():
    svc, store, port = make_service()
    intent = make_intent()
    result = svc.create_order(intent)
    assert result.status == OrderState.SUBMISSION_REQUESTED
    assert result.created is True
    assert result.duplicate is False
    assert result.client_order_id == f"ord-{intent.orchestration_id}"

    # durable order + 3 events (created, internal, submission)
    assert len(store.orders) == 1
    assert len(store.events) == 3
    statuses = [e.new_status for e in store.events]
    assert statuses == [
        OrderState.INTENT_CREATED.value,
        OrderState.INTERNAL_ORDER_CREATED.value,
        OrderState.SUBMISSION_REQUESTED.value,
    ]
    # execution boundary received exactly one handoff
    assert len(port.handoffs) == 1
    assert port.handoffs[0].order_id == result.order_id


def test_replay_returns_existing_order_no_second_order():
    svc, store, port = make_service()
    intent = make_intent()
    first = svc.create_order(intent)
    second = svc.create_order(intent)
    assert second.duplicate is True
    assert second.created is False
    assert second.order_id == first.order_id
    assert len(store.orders) == 1
    assert len(port.handoffs) == 1  # no second submission


def test_conflict_same_orchestration_different_payload_raises():
    svc, store, port = make_service()
    intent = make_intent(quantity="10")
    svc.create_order(intent)
    conflicting = replace(intent, quantity=Decimal("20"))
    with pytest.raises(IntentConflictError):
        svc.create_order(conflicting)
    assert len(store.orders) == 1


def test_live_mode_blocked_before_order_creation():
    svc, store, port = make_service()
    intent = make_intent(trading_mode="LIVE")
    with pytest.raises(TradingModeError):
        svc.create_order(intent)
    assert len(store.orders) == 0
    assert len(port.handoffs) == 0


def test_global_halt_blocks_order_creation():
    svc, store, port = make_service(halt=True)
    with pytest.raises(Exception):
        svc.create_order(make_intent())
    assert len(store.orders) == 0


def test_expired_approval_blocks_submission():
    svc, store, port = make_service()
    from alpha_algo_oms.errors import OrderValidationError

    with pytest.raises(OrderValidationError):
        svc.create_order(expired_intent())


def test_submission_recheck_rejects_expired_approval():
    # Defense-in-depth: approval valid at validation but expired by submission.
    from dataclasses import replace
    from datetime import timedelta
    from uuid import uuid4

    from alpha_algo_execution_engine.lifecycle import OrderLifecycle
    from alpha_algo_oms.identity import build_order_identity
    from alpha_algo_oms.validation import validate_intent

    svc, store, port = make_service()
    intent = make_intent()
    spec = validate_intent(intent, now=datetime.now(UTC), global_halt_active=False)
    expired = replace(
        spec, approval_expires_at=datetime.now(UTC) - timedelta(seconds=1)
    )
    identity = build_order_identity(intent, internal_order_id=uuid4(), quantity=spec.quantity)
    lifecycle = OrderLifecycle(order_id=uuid4()).transition_to(
        OrderState.INTERNAL_ORDER_CREATED, occurred_at=datetime.now(UTC), reason="x"
    )
    with pytest.raises(RiskApprovalError):
        svc._request_submission(lifecycle, expired)


def test_persistence_failure_is_no_false_success():
    svc, store, port = make_service(fail_commit=RuntimeError("db down"))
    with pytest.raises(PersistenceError):
        svc.create_order(make_intent())
    assert len(store.orders) == 0
    assert len(port.handoffs) == 0


def test_get_order_returns_status():
    svc, store, port = make_service()
    intent = make_intent()
    created = svc.create_order(intent)
    fetched = svc.get_order(created.order_id)
    assert fetched is not None
    assert fetched.order_id == created.order_id
    assert fetched.status == OrderState.SUBMISSION_REQUESTED


def test_get_order_missing_returns_none():
    from uuid import uuid4

    svc, store, port = make_service()
    assert svc.get_order(uuid4()) is None


def test_list_orders_returns_created_orders():
    svc, store, port = make_service()
    svc.create_order(make_intent())
    svc.create_order(make_intent())
    assert len(svc.list_orders()) == 2


def test_get_order_events_returns_history():
    svc, store, port = make_service()
    intent = make_intent()
    created = svc.create_order(intent)
    events = svc.get_order_events(created.order_id)
    assert len(events) == 3
    assert [e.event_type for e in events] == [
        "ORDER_CREATED",
        "INTERNAL_ORDER_CREATED",
        "SUBMISSION_REQUESTED",
    ]


def test_cancel_request_is_distinct_from_cancelled():
    svc, store, port = make_service()
    created = svc.create_order(make_intent())
    result = svc.request_cancellation(created.order_id)
    assert result.status == OrderState.CANCEL_REQUESTED
    assert result.status != OrderState.CANCELLED
    assert store.orders[created.order_id].status == OrderState.CANCEL_REQUESTED.value


def test_cancel_missing_order_raises_not_found():
    from uuid import uuid4

    svc, store, port = make_service()
    with pytest.raises(OrderNotFoundError):
        svc.request_cancellation(uuid4())


def test_cancel_after_terminal_state_rejected():
    svc, store, port = make_service()
    created = svc.create_order(make_intent())
    # manually mark terminal (FILLED) — the OMS itself never fabricates this
    store.orders[created.order_id].status = OrderState.FILLED.value
    with pytest.raises(InvalidStateTransitionError):
        svc.request_cancellation(created.order_id)


def test_cancel_from_intent_created_rejected():
    svc, store, port = make_service()
    created = svc.create_order(make_intent())
    store.orders[created.order_id].status = OrderState.INTENT_CREATED.value
    with pytest.raises(InvalidStateTransitionError):
        svc.request_cancellation(created.order_id)
