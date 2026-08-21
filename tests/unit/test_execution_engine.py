"""Phase 9 — ExecutionEngine submit/validation/idempotency tests."""

from datetime import UTC, datetime, timedelta

import pytest

from alpha_algo_execution_engine.adapter import (
    ExecutionResponse,
    InMemoryAdapter,
)
from alpha_algo_execution_engine.engine import ExecutionEngine
from alpha_algo_execution_engine.errors import ExecutionValidationError
from alpha_algo_execution_engine.lifecycle import OrderState
from alpha_algo_execution_engine.state import ExecutionSubmissionState

from execution_test_support import InMemoryExecutionRepository, make_request


def make_engine(adapter=None, repo=None, *, halt=False, max_retries=0):
    repo = repo if repo is not None else InMemoryExecutionRepository()
    engine = ExecutionEngine(
        adapter=adapter or InMemoryAdapter(),
        repository=repo,
        max_retries=max_retries,
        global_halt_active=lambda: halt,
    )
    return engine, repo, adapter or engine._adapter


def test_acknowledged_submission_maps_to_broker_acknowledged():
    engine, repo, adapter = make_engine()
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    outcome = engine.submit(req)
    assert outcome.submission_state == ExecutionSubmissionState.ACKNOWLEDGED
    assert outcome.order_state == OrderState.BROKER_ACKNOWLEDGED
    assert adapter.submissions == [req]


def test_live_mode_blocked():
    engine, repo, adapter = make_engine()
    with pytest.raises(ExecutionValidationError):
        engine.submit(make_request(trading_mode="LIVE"))
    assert adapter.submissions == []


def test_unknown_mode_blocked():
    engine, repo, adapter = make_engine()
    with pytest.raises(ExecutionValidationError):
        engine.submit(make_request(trading_mode="HACK"))
    assert adapter.submissions == []


def test_global_halt_blocks_submission():
    engine, repo, adapter = make_engine(halt=True)
    with pytest.raises(ExecutionValidationError):
        engine.submit(make_request())
    assert adapter.submissions == []


def test_expired_approval_blocked():
    engine, repo, adapter = make_engine()
    req = make_request(approval_expires_at=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(ExecutionValidationError):
        engine.submit(req)
    assert adapter.submissions == []


def test_missing_approval_blocked():
    engine, repo, adapter = make_engine()
    with pytest.raises(ExecutionValidationError):
        engine.submit(make_request(risk_approval_id=""))


def test_duplicate_submission_is_idempotent():
    engine, repo, adapter = make_engine()
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    first = engine.submit(req)
    second = engine.submit(req)
    assert second.duplicate is True
    assert second.order_id == first.order_id
    # only one real submission hit the adapter
    assert len(adapter.submissions) == 1


def test_rejected_response_maps_to_rejected():
    adapter = InMemoryAdapter(
        response=ExecutionResponse(
            status=ExecutionSubmissionState.REJECTED,
            reason="order rejected",
            occurred_at=datetime.now(UTC),
        )
    )
    engine, repo, _ = make_engine(adapter)
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    outcome = engine.submit(req)
    assert outcome.submission_state == ExecutionSubmissionState.REJECTED
    assert outcome.order_state == OrderState.REJECTED


def test_submitted_response_keeps_order_at_submission_requested():
    adapter = InMemoryAdapter(
        response=ExecutionResponse(
            status=ExecutionSubmissionState.SUBMITTED,
            reason="accepted, ack pending",
            occurred_at=datetime.now(UTC),
        )
    )
    engine, repo, _ = make_engine(adapter)
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    outcome = engine.submit(req)
    assert outcome.submission_state == ExecutionSubmissionState.SUBMITTED
    assert outcome.order_state == OrderState.SUBMISSION_REQUESTED


def test_attempt_is_persisted_and_finalized():
    engine, repo, adapter = make_engine()
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    engine.submit(req)
    attempt = repo.find_attempt(req.execution_id, 0)
    assert attempt is not None
    assert attempt.state == ExecutionSubmissionState.ACKNOWLEDGED
    assert attempt.broker_order_id is not None


def test_capabilities_reported_false_for_live():
    adapter = InMemoryAdapter()
    assert adapter.capabilities.supports_live_trading is False


def test_metrics_record_acknowledgment():
    engine, repo, adapter = make_engine()
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    engine.submit(req)
    assert engine._metrics.acknowledgments == 1
    assert engine._metrics.requests == 1
    assert engine._metrics.submissions == 1


def test_no_broker_specific_logic_in_engine_source():
    from pathlib import Path

    engine_dir = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "execution_engine"
        / "alpha_algo_execution_engine"
    )
    text = "\n".join(p.read_text(encoding="utf-8") for p in engine_dir.rglob("*.py")).lower()
    for forbidden in ("zerodha", "upstox", "alpaca", "ib_insync", "ccxt"):
        assert forbidden not in text, f"broker coupling: {forbidden}"
