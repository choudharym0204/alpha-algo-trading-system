"""Phase 6 — risk-event persistence (commit / rollback / duplicate)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from alpha_algo_contracts import RiskDecision, RiskDecisionResult
from alpha_algo_risk_engine.repository import (
    OUTCOME_DUPLICATE,
    OUTCOME_INSERTED,
    RiskEventRepository,
    to_orm_risk_event,
)
from alpha_algo_shared.db.models.safety import RiskEvent

from risk_test_support import FakeSessionFactory, make_buy_signal


def _decision(**overrides) -> RiskDecision:
    signal = make_buy_signal()
    return RiskDecision(
        request_id=uuid4(),
        signal_id=signal.signal_id,
        strategy_id=signal.strategy_id,
        instrument_id=signal.instrument_id,
        decision=RiskDecisionResult.APPROVED,
        reason_code="ALL_RULES_PASSED",
        reason="ok",
        rule_id="core.risk-rule-engine",
        evaluated_at=datetime.now(UTC),
        approval_id=uuid4(),
        expires_at=datetime.now(UTC),
        **overrides,
    )


def test_to_orm_risk_event_maps_fields():
    decision = _decision(binding_hash="b1", snapshot_id=uuid4())
    event = to_orm_risk_event(
        decision,
        account_id=uuid4(),
        trading_mode="PAPER",
        snapshot_id=decision.snapshot_id,
        identity_key="ik-1",
    )
    assert event.decision_id == decision.decision_id
    assert event.signal_id == decision.signal_id
    assert event.strategy_id == decision.strategy_id
    assert event.decision == "APPROVED"
    assert event.approval_id == str(decision.approval_id)
    assert event.binding_hash == "b1"
    assert event.identity_key == "ik-1"
    assert event.trading_mode == "PAPER"
    assert event.snapshot_id == decision.snapshot_id


def test_persist_inserts_when_not_found():
    factory = FakeSessionFactory(find_results=[None])
    repo = RiskEventRepository(factory)
    event = to_orm_risk_event(_decision(), identity_key="ik-insert")
    outcome, record_id = repo.persist(event)
    assert outcome == OUTCOME_INSERTED
    # record_id = event.id (not yet flushed by the fake, so None).
    assert record_id is None
    # Two sessions were created: find + persist.
    assert len(factory.sessions) == 2
    assert factory.sessions[1].committed is True


def test_persist_returns_duplicate_when_found():
    existing = RiskEvent(decision_id=uuid4(), identity_key="ik-dup")
    existing.id = uuid4()
    factory = FakeSessionFactory(find_results=[existing])
    repo = RiskEventRepository(factory)
    event = to_orm_risk_event(_decision(), identity_key="ik-dup")
    outcome, record_id = repo.persist(event)
    assert outcome == OUTCOME_DUPLICATE
    assert record_id == existing.id
    # Only the find session was created (no persist session).
    assert len(factory.sessions) == 1
    assert factory.sessions[0].committed is False


def test_persist_rolls_back_on_commit_failure():
    class Boom(Exception):
        pass

    factory = FakeSessionFactory(find_results=[None], commit_raises=Boom())
    repo = RiskEventRepository(factory)
    event = to_orm_risk_event(_decision(), identity_key="ik-rollback")
    with pytest.raises(Boom):
        repo.persist(event)
    # The persist session must have rolled back.
    assert factory.sessions[1].rolled_back is True
    assert factory.sessions[1].committed is False
