"""Phase 8 OMS — concurrency / idempotency-backstop tests."""

from datetime import UTC, datetime
from threading import Barrier, Thread
from uuid import uuid4

import pytest

from alpha_algo_execution_engine.lifecycle import OrderState
from alpha_algo_oms.boundary import ExecutionBoundary
from alpha_algo_oms.identity import build_order_identity
from alpha_algo_oms.repository import OrderRepository, to_orm_order
from alpha_algo_oms.service import OmsService
from alpha_algo_oms.validation import validate_intent

from oms_test_support import (
    InMemoryOmsStore,
    OmsSessionFactory,
    UniqueViolation,
    make_intent,
)


def _service(store):
    return OmsService(
        repository=OrderRepository(OmsSessionFactory(store)),
        execution_boundary=ExecutionBoundary(),
        global_halt_active=lambda: False,
    )


def test_concurrent_same_intent_yields_exactly_one_order():
    store = InMemoryOmsStore()
    svc = _service(store)
    intent = make_intent()

    results = []
    barrier = Barrier(2)

    def worker():
        barrier.wait()
        try:
            results.append(("ok", svc.create_order(intent)))
        except Exception as exc:  # noqa: BLE001
            results.append(("err", exc))

    threads = [Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ok_results = [r for tag, r in results if tag == "ok"]
    created = [r for r in ok_results if r.created]
    duplicates = [r for r in ok_results if r.duplicate]

    assert len(created) + len(duplicates) == 2
    assert len(created) == 1
    assert len(store.orders) == 1
    assert {r.order_id for r in ok_results} == {created[0].order_id}


def test_concurrent_different_intents_create_independent_orders():
    store = InMemoryOmsStore()
    svc = _service(store)
    intents = [make_intent(), make_intent()]

    results = []
    barrier = Barrier(2)

    def worker(i):
        barrier.wait()
        results.append(svc.create_order(intents[i]))

    threads = [Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(store.orders) == 2
    assert all(r.created for r in results)
    assert len({r.order_id for r in results}) == 2


def test_no_global_lock_serializes_distinct_orders():
    store = InMemoryOmsStore()
    svc = _service(store)
    a = svc.create_order(make_intent())
    b = svc.create_order(make_intent())
    assert a.order_id != b.order_id
    assert len(store.orders) == 2


def test_durable_backstop_rejects_duplicate_orchestration():
    store = InMemoryOmsStore()
    intent = make_intent()
    spec = validate_intent(intent, now=datetime.now(UTC), global_halt_active=False)
    ident = build_order_identity(intent, internal_order_id=uuid4(), quantity=spec.quantity)

    store.insert_order(to_orm_order(spec, ident))
    loser = to_orm_order(
        spec, build_order_identity(intent, internal_order_id=uuid4(), quantity=spec.quantity)
    )
    with pytest.raises(UniqueViolation):
        store.insert_order(loser)
    assert len(store.orders) == 1


def test_repository_converts_integrity_violation_to_duplicate():
    # Focused check: create_order already inserted the winner; a second create
    # with the same orchestration_id resolves via the find-first path.
    store = InMemoryOmsStore()
    repo = OrderRepository(OmsSessionFactory(store))
    intent = make_intent()
    spec = validate_intent(intent, now=datetime.now(UTC), global_halt_active=False)
    ident = build_order_identity(intent, internal_order_id=uuid4(), quantity=spec.quantity)
    order = to_orm_order(spec, ident)

    from alpha_algo_oms.repository import OUTCOME_CREATED, OUTCOME_DUPLICATE, to_orm_event

    event = to_orm_event(
        order_id=order.id, event_type="ORDER_CREATED", previous_status=None,
        new_status=OrderState.INTENT_CREATED.value, event_timestamp=datetime.now(UTC),
        reason="x", source_event_id=f"create-{spec.orchestration_id}",
    )
    assert repo.create_order(order, event)[0] == OUTCOME_CREATED

    order2 = to_orm_order(
        spec, build_order_identity(intent, internal_order_id=uuid4(), quantity=spec.quantity)
    )
    event2 = to_orm_event(
        order_id=order2.id, event_type="ORDER_CREATED", previous_status=None,
        new_status=OrderState.INTENT_CREATED.value, event_timestamp=datetime.now(UTC),
        reason="x", source_event_id=f"create-{spec.orchestration_id}-2",
    )
    outcome, oid = repo.create_order(order2, event2)
    assert outcome == OUTCOME_DUPLICATE
    assert oid == ident.internal_order_id
    assert len(store.orders) == 1
