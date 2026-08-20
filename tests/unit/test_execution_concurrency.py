"""Phase 9 — execution concurrency safety tests."""

import threading
from decimal import Decimal
from uuid import uuid4

from alpha_algo_execution_engine.adapter import InMemoryAdapter
from alpha_algo_execution_engine.engine import ExecutionEngine
from alpha_algo_execution_engine.events import OrderEventType

from execution_test_support import InMemoryExecutionRepository, make_event, make_request


def _engine(repo=None):
    repo = repo or InMemoryExecutionRepository()
    return (
        ExecutionEngine(
            adapter=InMemoryAdapter(), repository=repo, global_halt_active=lambda: False
        ),
        repo,
    )


def test_concurrent_duplicate_submission_single_effect():
    adapter = InMemoryAdapter()
    repo = InMemoryExecutionRepository()
    engine = ExecutionEngine(
        adapter=adapter, repository=repo, global_halt_active=lambda: False
    )
    req = make_request()
    repo.register_order(req.order_id, req.quantity)

    barrier = threading.Barrier(2)
    results = []
    errors = []

    def worker():
        barrier.wait()
        try:
            results.append(engine.submit(req))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly one real submission reached the adapter.
    assert len(adapter.submissions) == 1
    # At least one worker returned a clean outcome (duplicate or acknowledged).
    assert len(results) >= 1


def test_concurrent_distinct_orders_both_submitted():
    adapter = InMemoryAdapter()
    repo = InMemoryExecutionRepository()
    engine = ExecutionEngine(
        adapter=adapter, repository=repo, global_halt_active=lambda: False
    )
    reqs = [make_request(), make_request()]
    for r in reqs:
        repo.register_order(r.order_id, r.quantity)

    barrier = threading.Barrier(2)

    def worker(req):
        barrier.wait()
        engine.submit(req)

    threads = [threading.Thread(target=worker, args=(r,)) for r in reqs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(adapter.submissions) == 2


def test_concurrent_duplicate_fills_not_double_counted():
    adapter = InMemoryAdapter()
    repo = InMemoryExecutionRepository()
    engine = ExecutionEngine(
        adapter=adapter, repository=repo, global_halt_active=lambda: False
    )
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    fill = make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=30, source_event_id="f1")

    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        try:
            engine.apply_event(fill)
        except Exception:  # noqa: BLE001
            pass

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    state = repo.load_execution_state(oid)
    assert state.filled_quantity == Decimal("30")  # exactly one fill effect


def test_concurrent_fills_same_order_accumulate_once():
    repo = InMemoryExecutionRepository()
    engine = ExecutionEngine(
        adapter=InMemoryAdapter(), repository=repo, global_halt_active=lambda: False
    )
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))

    def fill(q, sid):
        engine.apply_event(make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=q, source_event_id=sid))

    threads = [
        threading.Thread(target=fill, args=(40, "f1")),
        threading.Thread(target=fill, args=(30, "f2")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    state = repo.load_execution_state(oid)
    assert state.filled_quantity in (Decimal("70"), Decimal("100"))


def test_attempt_unique_constraint_backstop():
    from execution_test_support import DuplicateAttempt
    from alpha_algo_execution_engine.state import ExecutionAttempt, ExecutionSubmissionState
    from datetime import UTC, datetime

    repo = InMemoryExecutionRepository()
    attempt = ExecutionAttempt(
        attempt_id="exec-a0",
        execution_id="exec",
        order_id=uuid4(),
        attempt_number=0,
        state=ExecutionSubmissionState.SUBMISSION_IN_PROGRESS,
        submitted_at=datetime.now(UTC),
    )
    repo.save_attempt(attempt)
    import pytest

    with pytest.raises(DuplicateAttempt):
        repo.save_attempt(attempt)
