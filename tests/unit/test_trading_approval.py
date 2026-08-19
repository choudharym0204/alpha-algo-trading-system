"""Phase 7 approval-handling + replay-safety tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alpha_algo_risk_engine.approval import compute_risk_identity_key
from alpha_algo_trading_engine.state import OrchestrationState

from trading_test_support import (
    FakeDecisionRiskService,
    RecordingOmsPort,
    buy_intent,
    make_approved_decision,
    make_buy_signal,
    make_orchestrator,
    make_signal_record,
)


def _approval_orchestrator(decision):
    risk = FakeDecisionRiskService(decision)
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(risk_service=risk, oms_port=port)
    return orchestrator, port


def test_valid_approval_proceeds():
    signal = make_buy_signal()
    intent = buy_intent("10")
    binding = compute_risk_identity_key(signal, intent, "PAPER")
    decision = make_approved_decision(signal, binding_hash=binding)
    orchestrator, port = _approval_orchestrator(decision)
    result = orchestrator.process_signal(
        make_signal_record(signal), trading_mode="PAPER", intent=intent
    )
    assert result.state == OrchestrationState.OMS_HANDOFF_READY
    assert result.intent.approval_id == decision.approval_id
    assert len(port.intents) == 1


def test_expired_approval_is_rejected():
    signal = make_buy_signal()
    intent = buy_intent("10")
    binding = compute_risk_identity_key(signal, intent, "PAPER")
    now = datetime.now(UTC)
    decision = make_approved_decision(
        signal,
        binding_hash=binding,
        evaluated_at=now - timedelta(seconds=60),
        expires_at=now - timedelta(seconds=30),
    )
    orchestrator, port = _approval_orchestrator(decision)
    result = orchestrator.process_signal(
        make_signal_record(signal), trading_mode="PAPER", intent=intent
    )
    assert result.state == OrchestrationState.REJECTED
    assert result.reason_code == "PRIOR_APPROVAL_INVALID"
    assert port.intents == []


def test_mismatched_approval_is_rejected():
    signal = make_buy_signal()
    intent = buy_intent("10")
    decision = make_approved_decision(signal, binding_hash="0" * 64)  # wrong binding
    orchestrator, port = _approval_orchestrator(decision)
    result = orchestrator.process_signal(
        make_signal_record(signal), trading_mode="PAPER", intent=intent
    )
    assert result.state == OrchestrationState.REJECTED
    assert result.reason_code == "PRIOR_APPROVAL_INVALID"
    assert port.intents == []


def test_replay_does_not_create_duplicate_intent():
    signal = make_buy_signal()
    intent = buy_intent("10")
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(oms_port=port)
    record = make_signal_record(signal)

    first = orchestrator.process_signal(record, trading_mode="PAPER", intent=intent)
    second = orchestrator.process_signal(record, trading_mode="PAPER", intent=intent)

    assert first.state == OrchestrationState.OMS_HANDOFF_READY
    assert second.state == OrchestrationState.DUPLICATE
    assert second.reason_code == "DUPLICATE_ORCHESTRATION"
    assert len(port.intents) == 1
    assert orchestrator.metrics.duplicates == 1


def test_replay_with_different_quantity_is_re_evaluated():
    signal = make_buy_signal()
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(oms_port=port)
    record = make_signal_record(signal)

    first = orchestrator.process_signal(record, trading_mode="PAPER", intent=buy_intent("10"))
    second = orchestrator.process_signal(record, trading_mode="PAPER", intent=buy_intent("20"))

    assert first.state == OrchestrationState.OMS_HANDOFF_READY
    assert second.state == OrchestrationState.OMS_HANDOFF_READY
    assert len(port.intents) == 2
    assert {i.quantity for i in port.intents} == {Decimal("10"), Decimal("20")}
