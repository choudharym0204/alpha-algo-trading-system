"""Phase 9 — execution event normalization + fill handling tests."""

from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_execution_engine.adapter import InMemoryAdapter
from alpha_algo_execution_engine.engine import ExecutionEngine
from alpha_algo_execution_engine.errors import ExecutionValidationError
from alpha_algo_execution_engine.events import (
    InvalidOrderEvent,
    OrderEventType,
)
from alpha_algo_execution_engine.lifecycle import OrderState

from execution_test_support import InMemoryExecutionRepository, make_event


def _engine(repo=None):
    repo = repo or InMemoryExecutionRepository()
    return (
        ExecutionEngine(
            adapter=InMemoryAdapter(), repository=repo, global_halt_active=lambda: False
        ),
        repo,
    )


def _acked(repo, oid, quantity=100):
    repo.register_order(oid, quantity)
    engine = ExecutionEngine(
        adapter=InMemoryAdapter(), repository=repo, global_halt_active=lambda: False
    )
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    return engine


def test_ack_event_maps_to_broker_acknowledged():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    state = engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    assert state.lifecycle.state == OrderState.BROKER_ACKNOWLEDGED


def test_reject_event_maps_to_rejected():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    state = engine.apply_event(make_event(oid, OrderEventType.REJECTED, source_event_id="rej"))
    assert state.lifecycle.state == OrderState.REJECTED


def test_partial_fills_accumulate():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    s1 = engine.apply_event(make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=30, source_event_id="f1"))
    assert s1.lifecycle.state == OrderState.PARTIALLY_FILLED
    assert s1.filled_quantity == Decimal("30")
    s2 = engine.apply_event(make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=40, source_event_id="f2"))
    assert s2.filled_quantity == Decimal("70")


def test_final_fill_completes_order():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    engine.apply_event(make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=70, source_event_id="f1"))
    final = engine.apply_event(make_event(oid, OrderEventType.FILL, fill_quantity=30, source_event_id="f2"))
    assert final.lifecycle.state == OrderState.FILLED
    assert final.filled_quantity == Decimal("100")


def test_fill_must_be_exact_quantity():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    with pytest.raises(InvalidOrderEvent):
        engine.apply_event(make_event(oid, OrderEventType.FILL, fill_quantity=50, source_event_id="bad"))


def test_overfill_is_rejected():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    with pytest.raises(InvalidOrderEvent):
        engine.apply_event(make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=120, source_event_id="over"))


def test_duplicate_event_has_no_effect():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    engine.apply_event(make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=30, source_event_id="f1"))
    # replay the same fill
    state = engine.apply_event(make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=30, source_event_id="f1"))
    assert state.filled_quantity == Decimal("30")  # no double-count
    assert len(repo.saved_events) == 2  # only ack + one fill persisted


def test_conflicting_duplicate_is_rejected():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    engine.apply_event(make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=30, source_event_id="f1"))
    with pytest.raises(ExecutionValidationError):
        engine.apply_event(
            make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=99, source_event_id="f1")
        )


def test_event_for_missing_order_is_rejected():
    engine, repo = _engine()
    with pytest.raises(ExecutionValidationError):
        engine.apply_event(make_event(uuid4(), OrderEventType.FILL, fill_quantity=10))


def test_fill_metrics_recorded():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    engine.apply_event(make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=30, source_event_id="f1"))
    engine.apply_event(make_event(oid, OrderEventType.FILL, fill_quantity=70, source_event_id="f2"))
    assert engine._metrics.partial_fills == 1
    assert engine._metrics.fills == 1
