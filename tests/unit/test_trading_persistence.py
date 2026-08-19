"""Phase 7 orchestration repository + DB-record mapping tests."""

from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_trading_engine.repository import (
    OUTCOME_DUPLICATE,
    OUTCOME_INSERTED,
    TradingIntentRepository,
    to_orm_rejection,
    to_orm_trading_intent,
)
from alpha_algo_trading_engine.service import _extract_limit_price
from alpha_algo_trading_engine.state import OrchestrationState

from risk_test_support import FakeSessionFactory
from trading_test_support import (
    buy_intent,
    make_buy_signal,
)


def test_extract_limit_price_handles_types():
    assert _extract_limit_price(buy_intent("10")) is None
    from alpha_algo_risk_engine.context import RiskOrderIntent

    assert _extract_limit_price(
        RiskOrderIntent(quantity=Decimal("10"), metadata={"limit_price": Decimal("99.5")})
    ) == Decimal("99.5")
    assert _extract_limit_price(
        RiskOrderIntent(quantity=Decimal("10"), metadata={"limit_price": "99.5"})
    ) == Decimal("99.5")
    assert _extract_limit_price(
        RiskOrderIntent(quantity=Decimal("10"), metadata={"limit_price": "not-a-number"})
    ) is None


def test_persist_inserts_when_not_present():
    repo = TradingIntentRepository(FakeSessionFactory(find_results=[None]))
    signal = make_buy_signal()
    intent = buy_intent("10")

    rec = to_orm_trading_intent(
        _sample_intent(signal, intent), state=OrchestrationState.OMS_HANDOFF_READY
    )
    outcome, rid = repo.persist(rec)
    assert outcome == OUTCOME_INSERTED
    # record_id = rec.id (not yet flushed by the fake session, so None).
    assert rid is None
    # the record was committed through the second session
    factory = repo._session_factory
    assert any(s.committed for s in factory.sessions)


def test_persist_detects_duplicate_without_insert():
    signal = make_buy_signal()
    intent = buy_intent("10")
    rec = to_orm_trading_intent(
        _sample_intent(signal, intent), state=OrchestrationState.OMS_HANDOFF_READY
    )
    # first find returns an existing record (same orchestration_id)
    repo = TradingIntentRepository(FakeSessionFactory(find_results=[rec]))
    outcome, rid = repo.persist(rec)
    assert outcome == OUTCOME_DUPLICATE
    assert rid == rec.id
    # only one session was created (the find); no commit occurred
    assert len(repo._session_factory.sessions) == 1
    assert not repo._session_factory.sessions[0].committed


def test_persist_commit_failure_rolls_back_and_raises():
    repo = TradingIntentRepository(FakeSessionFactory(commit_raises=RuntimeError("db down")))
    signal = make_buy_signal()
    intent = buy_intent("10")
    rec = to_orm_trading_intent(
        _sample_intent(signal, intent), state=OrchestrationState.OMS_HANDOFF_READY
    )
    with pytest.raises(RuntimeError):
        repo.persist(rec)
    # the second (insert) session rolled back, never committed
    assert repo._session_factory.sessions[1].rolled_back
    assert not repo._session_factory.sessions[1].committed


def test_to_orm_rejection_maps_core_fields():
    signal = make_buy_signal()
    intent = buy_intent("10", account_id=uuid4())
    rec = to_orm_rejection(
        signal, intent, "PAPER", "abc123", reason_code="X", reason="y"
    )
    assert rec.state == OrchestrationState.REJECTED.value
    assert rec.orchestration_id == "abc123"
    assert rec.signal_id == signal.signal_id
    assert rec.strategy_id == signal.strategy_id
    assert rec.instrument_id == signal.instrument_id
    assert rec.action == "BUY"
    assert rec.quantity == Decimal("10")
    assert rec.trading_mode == "PAPER"
    assert rec.reason_code == "X"


def test_trading_intent_model_metadata_column_matches_migration():
    from alpha_algo_shared.db.models.trading import TradingIntentRecord

    cols = set(TradingIntentRecord.__table__.columns.keys())
    assert "intent_metadata" in cols
    assert "metadata" not in cols


def _sample_intent(signal, intent):
    from alpha_algo_risk_engine.approval import compute_risk_identity_key
    from alpha_algo_signal_engine.identity import compute_signal_identity_key
    from alpha_algo_trading_engine.identity import compute_orchestration_identity_key

    binding = compute_risk_identity_key(signal, intent, "PAPER")
    from trading_test_support import make_approved_decision

    decision = make_approved_decision(signal, binding_hash=binding)
    from alpha_algo_trading_engine.intent import TradingIntent

    return TradingIntent(
        correlation_id=uuid4(),
        orchestration_id=compute_orchestration_identity_key(signal, intent, "PAPER"),
        account_id=intent.account_id,
        strategy_id=signal.strategy_id,
        strategy_version=signal.strategy_version,
        strategy_config_hash=signal.strategy_config_hash,
        strategy_run_id=None,
        signal_id=signal.signal_id,
        signal_identity_key=compute_signal_identity_key(signal),
        instrument_id=signal.instrument_id,
        action=signal.action.value,
        quantity=intent.quantity,
        order_type=intent.order_type,
        limit_price=None,
        trading_mode="PAPER",
        risk_decision_id=decision.decision_id,
        approval_id=decision.approval_id,
        approval_expires_at=decision.expires_at,
        binding_hash=binding,
        metadata={},
    )
