"""Phase 9 — submission state machine + restart recovery tests."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from alpha_algo_execution_engine.adapter import (
    ExecutionResponse,
    InMemoryAdapter,
)
from alpha_algo_execution_engine.engine import ExecutionEngine
from alpha_algo_execution_engine.errors import ExecutionValidationError
from alpha_algo_execution_engine.events import InvalidOrderEvent, OrderEventType
from alpha_algo_execution_engine.lifecycle import OrderState
from alpha_algo_execution_engine.state import ExecutionSubmissionState

from execution_test_support import InMemoryExecutionRepository, make_event, make_request


def _engine(repo=None, adapter=None):
    repo = repo or InMemoryExecutionRepository()
    return (
        ExecutionEngine(
            adapter=adapter or InMemoryAdapter(),
            repository=repo,
            global_halt_active=lambda: False,
        ),
        repo,
    )


def test_submission_state_enum_values():
    assert ExecutionSubmissionState.SUBMISSION_REQUESTED.value == "SUBMISSION_REQUESTED"
    assert ExecutionSubmissionState.SUBMISSION_IN_PROGRESS.value == "SUBMISSION_IN_PROGRESS"
    assert ExecutionSubmissionState.SUBMITTED.value == "SUBMITTED"
    assert ExecutionSubmissionState.ACKNOWLEDGED.value == "ACKNOWLEDGED"
    assert ExecutionSubmissionState.TIMEOUT.value == "TIMEOUT"
    assert ExecutionSubmissionState.REJECTED.value == "REJECTED"
    assert ExecutionSubmissionState.UNKNOWN.value == "UNKNOWN"
    assert ExecutionSubmissionState.CANCELLED.value == "CANCELLED"


def test_invalid_transition_rejected():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    # CANCEL_REQUESTED from SUBMISSION_REQUESTED is invalid (no ack yet).
    with pytest.raises(Exception):
        engine.apply_event(make_event(oid, OrderEventType.CANCELLED))


def test_forged_transition_blocked():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    # Direct FILL without ACK is invalid -> InvalidOrderEvent.
    with pytest.raises(Exception):
        engine.apply_event(make_event(oid, OrderEventType.FILL, fill_quantity=100))


def test_restart_recovery_after_ack():
    repo = InMemoryExecutionRepository()
    engine, _ = _engine(repo)
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))

    # Simulate restart: a fresh engine bound to the same durable repo.
    engine2, _ = _engine(repo)
    state = engine2._repository.load_execution_state(oid)
    assert state is not None
    assert state.lifecycle.state == OrderState.BROKER_ACKNOWLEDGED


def test_restart_recovery_after_partial_fill():
    from decimal import Decimal

    repo = InMemoryExecutionRepository()
    engine, _ = _engine(repo)
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    engine.apply_event(make_event(oid, OrderEventType.PARTIAL_FILL, fill_quantity=40, source_event_id="f1"))

    engine2, _ = _engine(repo)
    state = engine2._repository.load_execution_state(oid)
    assert state.filled_quantity == Decimal("40")
    assert state.lifecycle.state == OrderState.PARTIALLY_FILLED


def test_restart_recovery_after_fill():
    repo = InMemoryExecutionRepository()
    engine, _ = _engine(repo)
    oid = uuid4()
    repo.register_order(oid, 100)
    engine.apply_event(make_event(oid, OrderEventType.BROKER_ACKNOWLEDGED, source_event_id="ack"))
    engine.apply_event(make_event(oid, OrderEventType.FILL, fill_quantity=100, source_event_id="f1"))

    engine2, _ = _engine(repo)
    state = engine2._repository.load_execution_state(oid)
    assert state.lifecycle.state == OrderState.FILLED


def test_attempt_record_survives_restart():
    adapter = InMemoryAdapter()
    repo = InMemoryExecutionRepository()
    engine = ExecutionEngine(
        adapter=adapter, repository=repo, global_halt_active=lambda: False
    )
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    engine.submit(req)

    engine2 = ExecutionEngine(
        adapter=InMemoryAdapter(), repository=repo, global_halt_active=lambda: False
    )
    attempt = engine2._repository.find_attempt(req.execution_id, 0)
    assert attempt is not None
    assert attempt.state == ExecutionSubmissionState.ACKNOWLEDGED


def test_invalid_order_event_is_typed():
    assert issubclass(InvalidOrderEvent, ValueError) or issubclass(
        InvalidOrderEvent, Exception
    )
