"""Phase 6 — RiskService end-to-end flow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alpha_algo_contracts import RiskDecisionResult
from alpha_algo_risk_engine.circuit_breaker import CircuitBreakerConfig, CircuitBreakerRegistry
from alpha_algo_risk_engine.context import RiskOrderIntent
from alpha_algo_risk_engine.repository import RiskEventRepository
from alpha_algo_risk_engine.service import RiskService

from risk_test_support import (
    FakeRiskProvider,
    FakeSessionFactory,
    healthy_account,
    make_buy_signal,
    make_snapshot,
)


def _svc(provider=None, repository=None, circuit_breaker=None):
    return RiskService(
        provider=provider or FakeRiskProvider(),
        repository=repository,
        circuit_breaker=circuit_breaker or CircuitBreakerRegistry(),
    )


def test_approve_happy_path():
    svc = _svc()
    outcome = svc.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert outcome.status == "APPROVED"
    assert outcome.decision.decision == RiskDecisionResult.APPROVED
    assert outcome.decision.approval_id is not None
    assert outcome.decision.expires_at is not None
    assert outcome.decision.binding_hash is not None
    assert outcome.decision.snapshot_id is not None


def test_global_halt_rejects_everything():
    svc = _svc(provider=FakeRiskProvider(make_snapshot(global_halt_active=True)))
    outcome = svc.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert outcome.status == "REJECTED"
    assert outcome.decision.reason_code == "GLOBAL_HALT_ACTIVE"
    assert outcome.decision.rule_id == "core.global-halt"


def test_live_mode_rejected_at_boundary():
    svc = _svc()
    outcome = svc.evaluate(make_buy_signal(), trading_mode="LIVE")
    assert outcome.status == "REJECTED"
    assert outcome.decision.reason_code == "LIVE_MODE_BLOCKED"


def test_unknown_mode_rejected_at_boundary():
    svc = _svc()
    outcome = svc.evaluate(make_buy_signal(), trading_mode="PROD")
    assert outcome.status == "REJECTED"
    assert outcome.decision.reason_code == "LIVE_MODE_BLOCKED"


def test_circuit_breaker_open_rejects():
    breaker = CircuitBreakerRegistry(CircuitBreakerConfig(failure_threshold=1))
    breaker.record_failure("global")
    svc = _svc(circuit_breaker=breaker)
    outcome = svc.evaluate(make_buy_signal())
    assert outcome.status == "REJECTED"
    assert outcome.decision.reason_code == "CIRCUIT_BREAKER_OPEN"
    assert svc.metrics.circuit_breaker_trips == 1


def test_context_unavailable_rejects():
    svc = _svc(provider=FakeRiskProvider(make_snapshot(state_available=False)))
    outcome = svc.evaluate(make_buy_signal())
    assert outcome.status == "REJECTED"
    assert outcome.decision.reason_code == "RISK_STATE_UNAVAILABLE"


def test_context_invalid_rejects():
    provider = FakeRiskProvider(make_snapshot(account=healthy_account(equity=Decimal("-1"))))
    svc = _svc(provider=provider)
    outcome = svc.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert outcome.status == "REJECTED"
    assert outcome.decision.reason_code == "RISK_CONTEXT_INVALID"


def test_duplicate_returns_prior_decision():
    svc = _svc()
    signal = make_buy_signal()
    first = svc.evaluate(signal, intent=RiskOrderIntent(quantity=Decimal("10")))
    second = svc.evaluate(signal, intent=RiskOrderIntent(quantity=Decimal("10")))
    assert second.status == "DUPLICATE"
    assert second.prior_decision_id == first.decision.decision_id
    assert second.decision.approval_id == first.decision.approval_id
    assert svc.metrics.duplicates == 1


def test_duplicate_does_not_create_new_approval():
    svc = _svc()
    signal = make_buy_signal()
    first = svc.evaluate(signal, intent=RiskOrderIntent(quantity=Decimal("10")))
    second = svc.evaluate(signal, intent=RiskOrderIntent(quantity=Decimal("10")))
    assert second.decision.approval_id == first.decision.approval_id


def test_fan_out_only_on_approval_and_once():
    svc = _svc()
    received = []
    svc.add_consumer(lambda d: received.append(d))

    signal = make_buy_signal()
    svc.evaluate(signal, intent=RiskOrderIntent(quantity=Decimal("10")))
    svc.evaluate(signal, intent=RiskOrderIntent(quantity=Decimal("10")))  # duplicate
    assert len(received) == 1
    assert received[0].decision == RiskDecisionResult.APPROVED


def test_fan_out_not_called_on_rejection():
    svc = _svc(provider=FakeRiskProvider(make_snapshot(global_halt_active=True)))
    received = []
    svc.add_consumer(lambda d: received.append(d))
    svc.evaluate(make_buy_signal())
    assert received == []


def test_persistence_success_marks_persisted():
    repo = RiskEventRepository(FakeSessionFactory(find_results=[None]))
    svc = _svc(repository=repo)
    outcome = svc.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert outcome.persisted is True


def test_persistence_failure_does_not_false_commit():
    class Boom(Exception):
        pass

    repo = RiskEventRepository(FakeSessionFactory(find_results=[None], commit_raises=Boom()))
    svc = _svc(repository=repo)
    received = []
    svc.add_consumer(lambda d: received.append(d))
    outcome = svc.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert outcome.status == "APPROVED"  # decision itself is deterministic/valid
    assert outcome.persisted is False  # but NOT durably committed
    assert svc.metrics.persistence_failures == 1
    # No durable commit → the approval must not be fanned out.
    assert received == []


def test_different_quantity_is_not_deduplicated():
    svc = _svc()
    signal = make_buy_signal()
    first = svc.evaluate(signal, intent=RiskOrderIntent(quantity=Decimal("10")))
    second = svc.evaluate(signal, intent=RiskOrderIntent(quantity=Decimal("2000")))
    assert first.status == "APPROVED"
    assert second.status == "REJECTED"
    assert second.decision.reason_code == "QUANTITY_LIMIT_EXCEEDED"


def test_replay_after_approval_expiry_is_rejected():
    start = datetime.now(UTC)
    state = {"now": start}
    svc = RiskService(provider=FakeRiskProvider(), clock=lambda: state["now"])
    signal = make_buy_signal()
    first = svc.evaluate(signal, intent=RiskOrderIntent(quantity=Decimal("10")))
    assert first.status == "APPROVED"

    state["now"] = start + timedelta(seconds=60)  # past the 30s approval TTL
    second = svc.evaluate(signal, intent=RiskOrderIntent(quantity=Decimal("10")))
    assert second.status == "REJECTED"
    assert second.decision.reason_code == "PRIOR_APPROVAL_INVALID"


def test_provider_trading_mode_mismatch_rejects():
    provider = FakeRiskProvider(make_snapshot(trading_mode="LIVE"))
    svc = _svc(provider=provider)
    outcome = svc.evaluate(make_buy_signal(), intent=RiskOrderIntent(quantity=Decimal("10")))
    assert outcome.status == "REJECTED"
    assert outcome.decision.reason_code == "RISK_STATE_UNAVAILABLE"


def test_snapshot_account_mismatch_rejects():
    requested = uuid4()
    other = uuid4()
    provider = FakeRiskProvider(make_snapshot(account=healthy_account(account_id=other)))
    svc = _svc(provider=provider)
    outcome = svc.evaluate(
        make_buy_signal(),
        intent=RiskOrderIntent(quantity=Decimal("10"), account_id=requested),
    )
    assert outcome.status == "REJECTED"
    assert outcome.decision.reason_code == "RISK_STATE_UNAVAILABLE"


def test_rejection_rule_recorded_in_metrics():
    provider = FakeRiskProvider(make_snapshot(global_halt_active=True))
    svc = _svc(provider=provider)
    svc.evaluate(make_buy_signal())
    assert svc.metrics.rejections == 1
    assert svc.metrics.by_rule["core.global-halt"] == 1


def test_metrics_track_evaluations():
    svc = _svc()
    svc.evaluate(make_buy_signal())
    svc.evaluate(make_buy_signal())
    assert svc.metrics.evaluations == 2
