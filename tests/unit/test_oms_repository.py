"""Phase 8 OMS — repository transactional persistence tests."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from alpha_algo_execution_engine.lifecycle import OrderState
from alpha_algo_oms.identity import build_order_identity
from alpha_algo_oms.repository import (
    OUTCOME_CREATED,
    OUTCOME_DUPLICATE,
    OrderRepository,
    to_orm_event,
    to_orm_order,
)
from alpha_algo_oms.validation import validate_intent

from oms_test_support import (
    InMemoryOmsStore,
    OmsSessionFactory,
    UniqueViolation,
    make_intent,
)


def _now():
    return datetime.now(UTC)


def _build(intent):
    spec = validate_intent(intent, now=_now(), global_halt_active=False)
    identity = build_order_identity(intent, internal_order_id=uuid4(), quantity=spec.quantity)
    return spec, identity, to_orm_order(spec, identity)


def _initial_event(order_id, orchestration_id):
    return to_orm_event(
        order_id=order_id,
        event_type="ORDER_CREATED",
        previous_status=None,
        new_status=OrderState.INTENT_CREATED.value,
        event_timestamp=_now(),
        reason="created",
        source_event_id=f"create-{orchestration_id}",
    )


def test_create_order_inserts_order_and_event():
    store = InMemoryOmsStore()
    repo = OrderRepository(OmsSessionFactory(store))
    intent = make_intent()
    spec, identity, order = _build(intent)
    outcome, oid = repo.create_order(order, _initial_event(order.id, spec.orchestration_id))
    assert outcome == OUTCOME_CREATED
    assert oid == identity.internal_order_id
    assert len(store.orders) == 1
    assert len(store.events) == 1
    assert store.events[0].order_id == identity.internal_order_id


def test_create_order_detects_duplicate_orchestration():
    store = InMemoryOmsStore()
    repo = OrderRepository(OmsSessionFactory(store))
    intent = make_intent()
    spec, identity, order = _build(intent)
    assert repo.create_order(order, _initial_event(order.id, spec.orchestration_id))[0] == OUTCOME_CREATED

    order2 = to_orm_order(spec, build_order_identity(intent, internal_order_id=uuid4(), quantity=spec.quantity))
    outcome, oid = repo.create_order(order2, _initial_event(order2.id, spec.orchestration_id))
    assert outcome == OUTCOME_DUPLICATE
    assert oid == identity.internal_order_id
    assert len(store.orders) == 1


def test_create_order_commit_failure_rolls_back():
    store = InMemoryOmsStore()
    sf = OmsSessionFactory(store, fail_commit=RuntimeError("db down"))
    repo = OrderRepository(sf)
    intent = make_intent()
    spec, identity, order = _build(intent)
    with pytest.raises(RuntimeError):
        repo.create_order(order, _initial_event(order.id, spec.orchestration_id))
    assert len(store.orders) == 0
    assert len(store.events) == 0


def test_append_event_updates_status_and_adds_event():
    store = InMemoryOmsStore()
    repo = OrderRepository(OmsSessionFactory(store))
    intent = make_intent()
    spec, identity, order = _build(intent)
    repo.create_order(order, _initial_event(order.id, spec.orchestration_id))

    ev = to_orm_event(
        order_id=order.id, event_type="INTERNAL_ORDER_CREATED",
        previous_status=OrderState.INTENT_CREATED.value,
        new_status=OrderState.INTERNAL_ORDER_CREATED.value,
        event_timestamp=_now(), reason="x", source_event_id="x-internal",
    )
    repo.append_event(order.id, ev, new_status=OrderState.INTERNAL_ORDER_CREATED.value)
    assert store.orders[order.id].status == OrderState.INTERNAL_ORDER_CREATED.value
    assert len(store.events) == 2


def test_append_event_missing_order_raises():
    store = InMemoryOmsStore()
    repo = OrderRepository(OmsSessionFactory(store))
    ev = to_orm_event(
        order_id=uuid4(), event_type="X", previous_status=None, new_status="Y",
        event_timestamp=_now(), reason="x",
    )
    with pytest.raises(KeyError):
        repo.append_event(ev.order_id, ev, new_status="Y")


def test_get_events_returns_in_insertion_order():
    store = InMemoryOmsStore()
    repo = OrderRepository(OmsSessionFactory(store))
    intent = make_intent()
    spec, identity, order = _build(intent)
    repo.create_order(order, _initial_event(order.id, spec.orchestration_id))
    events = repo.get_events(order.id)
    assert len(events) == 1
    assert events[0].event_type == "ORDER_CREATED"


def test_unique_constraint_backstops_duplicate_insert():
    store = InMemoryOmsStore()
    intent = make_intent()
    spec, identity, order = _build(intent)
    store.insert_order(order)
    dup = to_orm_order(spec, build_order_identity(intent, internal_order_id=uuid4(), quantity=spec.quantity))
    with pytest.raises(UniqueViolation):
        store.insert_order(dup)


def test_find_by_orchestration_id_returns_none_when_absent():
    store = InMemoryOmsStore()
    repo = OrderRepository(OmsSessionFactory(store))
    assert repo.find_by_orchestration_id("missing") is None


def test_find_by_id_returns_order():
    store = InMemoryOmsStore()
    repo = OrderRepository(OmsSessionFactory(store))
    intent = make_intent()
    spec, identity, order = _build(intent)
    repo.create_order(order, _initial_event(order.id, spec.orchestration_id))
    found = repo.find_by_id(order.id)
    assert found is not None
    assert found.id == order.id
