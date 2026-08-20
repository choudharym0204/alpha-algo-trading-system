"""Phase 9 — execution cancellation lifecycle tests."""

from datetime import UTC, datetime
from uuid import uuid4

from alpha_algo_execution_engine.adapter import (
    ExecutionCapabilities,
    ExecutionResponse,
    InMemoryAdapter,
)
from alpha_algo_execution_engine.engine import ExecutionEngine
from alpha_algo_execution_engine.lifecycle import OrderState
from alpha_algo_execution_engine.state import ExecutionSubmissionState

from execution_test_support import InMemoryExecutionRepository


def _engine(adapter, repo=None):
    repo = repo or InMemoryExecutionRepository()
    return (
        ExecutionEngine(
            adapter=adapter, repository=repo, global_halt_active=lambda: False
        ),
        repo,
    )


def _cancelled_response() -> ExecutionResponse:
    return ExecutionResponse(
        status=ExecutionSubmissionState.CANCELLED,
        reason="cancelled",
        occurred_at=datetime.now(UTC),
    )


def test_cancellation_confirm_maps_to_cancelled():
    adapter = InMemoryAdapter(cancel_response=_cancelled_response())
    engine, repo = _engine(adapter)
    oid = uuid4()
    repo.register_order(oid)
    outcome = engine.cancel(oid)
    assert outcome.order_state == OrderState.CANCELLED
    assert adapter.cancellations == [oid]


def test_cancellation_pending_maps_to_unknown_not_cancelled():
    adapter = InMemoryAdapter()  # default cancel -> UNKNOWN (pending)
    engine, repo = _engine(adapter)
    oid = uuid4()
    repo.register_order(oid)
    outcome = engine.cancel(oid)
    assert outcome.order_state == OrderState.UNKNOWN
    assert outcome.order_state != OrderState.CANCELLED


def test_cancellation_rejected_stays_cancel_requested():
    adapter = InMemoryAdapter(
        cancel_response=ExecutionResponse(
            status=ExecutionSubmissionState.REJECTED,
            reason="cancel rejected",
            occurred_at=datetime.now(UTC),
        )
    )
    engine, repo = _engine(adapter)
    oid = uuid4()
    repo.register_order(oid)
    outcome = engine.cancel(oid)
    assert outcome.order_state == OrderState.CANCEL_REQUESTED


def test_cancellation_unsupported_rejected():
    adapter = InMemoryAdapter(
        capabilities=ExecutionCapabilities(supports_cancellation=False)
    )
    engine, repo = _engine(adapter)
    outcome = engine.cancel(uuid4())
    assert outcome.submission_state == ExecutionSubmissionState.REJECTED
    assert adapter.cancellations == []


def test_cancel_records_metric():
    adapter = InMemoryAdapter(cancel_response=_cancelled_response())
    engine, repo = _engine(adapter)
    oid = uuid4()
    repo.register_order(oid)
    engine.cancel(oid)
    assert engine._metrics.cancellations == 1
