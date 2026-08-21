"""Phase 9 — timeout semantics + retry classification tests."""



from alpha_algo_execution_engine.adapter import InMemoryAdapter
from alpha_algo_execution_engine.engine import ExecutionEngine
from alpha_algo_execution_engine.errors import (
    ExecutionAuthError,
    ExecutionTimeoutError,
    ExecutionTransientError,
    FailureClass,
)
from alpha_algo_execution_engine.lifecycle import OrderState
from alpha_algo_execution_engine.state import ExecutionSubmissionState

from execution_test_support import InMemoryExecutionRepository, make_request


def make_engine(adapter, repo=None, *, max_retries=0):
    repo = repo or InMemoryExecutionRepository()
    return (
        ExecutionEngine(
            adapter=adapter,
            repository=repo,
            max_retries=max_retries,
            global_halt_active=lambda: False,
        ),
        repo,
    )


def test_timeout_maps_to_unknown_not_rejected():
    adapter = InMemoryAdapter(raise_error=ExecutionTimeoutError("response timeout"))
    engine, repo = make_engine(adapter)
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    outcome = engine.submit(req)
    assert outcome.submission_state == ExecutionSubmissionState.TIMEOUT
    assert outcome.order_state == OrderState.UNKNOWN
    assert outcome.order_state != OrderState.REJECTED


def test_timeout_does_not_blind_retry():
    adapter = InMemoryAdapter(raise_error=ExecutionTimeoutError("response timeout"))
    engine, repo = make_engine(adapter, max_retries=3)
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    engine.submit(req)
    # exactly one dispatch — timeout is ambiguous, never blind-retried
    assert len(adapter.submissions) == 1


def test_transient_error_retries_within_bounds():
    adapter = InMemoryAdapter(raise_error=ExecutionTransientError("temporary"))
    engine, repo = make_engine(adapter, max_retries=2)
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    outcome = engine.submit(req)
    # 1 initial + 2 retries = 3 attempts
    assert len(adapter.submissions) == 3
    assert outcome.submission_state == ExecutionSubmissionState.REJECTED


def test_transient_error_exhausts_retries_no_false_success():
    adapter = InMemoryAdapter(raise_error=ExecutionTransientError("temporary"))
    engine, repo = make_engine(adapter, max_retries=2)
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    outcome = engine.submit(req)
    assert engine._metrics.retries == 2
    assert outcome.order_state is None  # no order lifecycle claim on failure


def test_auth_error_is_not_retried():
    adapter = InMemoryAdapter(raise_error=ExecutionAuthError("bad credentials"))
    engine, repo = make_engine(adapter, max_retries=3)
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    engine.submit(req)
    assert len(adapter.submissions) == 1  # auth failure is permanent


def test_failure_classification():
    from alpha_algo_execution_engine.errors import classify

    assert classify(ExecutionTimeoutError("x")) == FailureClass.TIMEOUT
    assert classify(ExecutionTransientError("x")) == FailureClass.TRANSIENT_FAILURE
    assert classify(ExecutionAuthError("x")) == FailureClass.AUTH_FAILURE
    assert classify(TimeoutError("x")) == FailureClass.TIMEOUT
    assert classify(RuntimeError("x")) == FailureClass.INTERNAL_FAILURE


def test_only_transient_is_retryable():
    from alpha_algo_execution_engine.errors import RETRYABLE_FAILURE_CLASSES

    assert RETRYABLE_FAILURE_CLASSES == frozenset({FailureClass.TRANSIENT_FAILURE})


def test_metrics_record_timeout():
    adapter = InMemoryAdapter(raise_error=ExecutionTimeoutError("timeout"))
    engine, repo = make_engine(adapter)
    req = make_request()
    repo.register_order(req.order_id, req.quantity)
    engine.submit(req)
    assert engine._metrics.timeouts == 1
    assert engine._metrics.unknown_states >= 1
