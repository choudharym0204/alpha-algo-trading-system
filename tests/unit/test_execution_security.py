"""Phase 9 — execution security tests (LIVE blocked, forged events, no bypass)."""

from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_execution_engine.adapter import InMemoryAdapter
from alpha_algo_execution_engine.engine import ExecutionEngine
from alpha_algo_execution_engine.errors import ExecutionValidationError
from alpha_algo_execution_engine.events import OrderEventType
from alpha_algo_execution_engine.lifecycle import OrderState

from execution_test_support import InMemoryExecutionRepository, make_event, make_request


def _engine(repo=None):
    repo = repo or InMemoryExecutionRepository()
    return (
        ExecutionEngine(
            adapter=InMemoryAdapter(), repository=repo, global_halt_active=lambda: False
        ),
        repo,
    )


def test_live_request_blocked_at_dispatch():
    engine, repo = _engine()
    with pytest.raises(ExecutionValidationError):
        engine.submit(make_request(trading_mode="LIVE"))


def test_forged_fill_event_rejected_for_unknown_order():
    engine, repo = _engine()
    with pytest.raises(ExecutionValidationError):
        engine.apply_event(make_event(uuid4(), OrderEventType.FILL, fill_quantity=10))


def test_client_cannot_force_filled_directly():
    engine, repo = _engine()
    oid = uuid4()
    repo.register_order(oid, 100)
    # A raw FILL before ACK is an invalid transition -> rejected.
    with pytest.raises(Exception):
        engine.apply_event(make_event(oid, OrderEventType.FILL, fill_quantity=100))


def test_approval_cannot_be_bypassed():
    from dataclasses import replace

    engine, repo = _engine()
    with pytest.raises(ExecutionValidationError):
        engine.submit(make_request(risk_approval_id=""))
    with pytest.raises(ExecutionValidationError):
        engine.submit(replace(make_request(), risk_approval_id=None))


def test_unknown_trading_mode_fails_closed():
    engine, repo = _engine()
    with pytest.raises(ExecutionValidationError):
        engine.submit(make_request(trading_mode="SANDBOX"))


def test_global_halt_blocks_everything():
    engine = ExecutionEngine(
        adapter=InMemoryAdapter(),
        repository=InMemoryExecutionRepository(),
        global_halt_active=lambda: True,
    )
    with pytest.raises(ExecutionValidationError):
        engine.submit(make_request())


def test_no_broker_credentials_in_engine():
    from pathlib import Path

    engine_dir = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "execution_engine"
        / "alpha_algo_execution_engine"
    )
    text = "\n".join(p.read_text(encoding="utf-8") for p in engine_dir.rglob("*.py")).lower()
    for forbidden in ("api_key", "api_secret", "access_token", "password"):
        assert forbidden not in text, f"credential leakage: {forbidden}"


def test_in_memory_adapter_is_explicitly_test_only():
    from alpha_algo_execution_engine.adapter import InMemoryAdapter

    assert InMemoryAdapter.__name__ == "InMemoryAdapter"
    assert "TEST" in InMemoryAdapter.__doc__ or InMemoryAdapter.capabilities.provider_name == "test"
