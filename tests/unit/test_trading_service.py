"""Phase 7 trading-orchestrator golden-flow + failure-handling tests."""

from decimal import Decimal


from alpha_algo_contracts import SignalAction
from alpha_algo_risk_engine.approval import compute_risk_identity_key
from alpha_algo_signal_engine.state import SignalState
from alpha_algo_trading_engine.identity import compute_orchestration_identity_key
from alpha_algo_trading_engine.state import OrchestrationState

from risk_test_support import FakeRiskProvider, FakeSessionFactory, make_snapshot
from signal_test_support import make_signal
from trading_test_support import (
    FailingOmsPort,
    FixedIntentResolver,
    RecordingOmsPort,
    buy_intent,
    make_buy_signal,
    make_orchestrator,
    make_signal_record,
)


def test_happy_path_accepted_signal_to_oms_handoff():
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(oms_port=port)
    record = make_signal_record()
    signal = record.signal
    intent = buy_intent("10")

    result = orchestrator.process_signal(record, trading_mode="PAPER", intent=intent)

    assert result.state == OrchestrationState.OMS_HANDOFF_READY
    assert result.handoff_delivered is True
    assert len(port.intents) == 1

    t = result.intent
    assert t.signal_id == signal.signal_id
    assert t.strategy_id == signal.strategy_id
    assert t.instrument_id == signal.instrument_id
    assert t.action == "BUY"
    assert t.quantity == Decimal("10")
    assert t.order_type == "MARKET"
    assert t.trading_mode == "PAPER"
    assert t.approval_id is not None
    assert t.approval_expires_at is not None
    assert t.risk_decision_id is not None
    assert t.correlation_id is not None
    assert t.binding_hash == compute_risk_identity_key(signal, intent, "PAPER")
    assert t.orchestration_id == compute_orchestration_identity_key(signal, intent, "PAPER")
    assert t.signal_identity_key == record.identity_key


def test_exit_is_represented_correctly():
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(oms_port=port)
    signal = make_signal(action=SignalAction.EXIT)
    record = make_signal_record(signal)
    result = orchestrator.process_signal(record, trading_mode="PAPER", intent=buy_intent("5"))
    assert result.state == OrchestrationState.OMS_HANDOFF_READY
    assert result.intent.action == "EXIT"


def test_sell_is_represented_correctly():
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(oms_port=port)
    signal = make_signal(action=SignalAction.SELL)
    record = make_signal_record(signal)
    result = orchestrator.process_signal(record, trading_mode="PAPER", intent=buy_intent("5"))
    assert result.state == OrchestrationState.OMS_HANDOFF_READY
    assert result.intent.action == "SELL"


def test_non_persisted_signal_is_rejected():
    orchestrator = make_orchestrator()
    record = make_signal_record(state=SignalState.REJECTED)
    result = orchestrator.process_signal(record, trading_mode="PAPER")
    assert result.state == OrchestrationState.REJECTED
    assert result.reason_code == "SIGNAL_NOT_ACCEPTED"
    assert result.intent is None


def test_identity_mismatch_is_rejected():
    orchestrator = make_orchestrator()
    signal = make_buy_signal()
    # build a record whose identity_key belongs to a DIFFERENT signal
    other = make_signal_record(signal)
    record = make_signal_record()
    from alpha_algo_signal_engine.service import SignalRecord

    record = SignalRecord(
        signal=signal,
        record_id=other.record_id,
        identity_key="0" * 64,
        state=SignalState.PERSISTED,
    )
    result = orchestrator.process_signal(record, trading_mode="PAPER", intent=buy_intent("10"))
    assert result.state == OrchestrationState.REJECTED
    assert result.reason_code == "SIGNAL_IDENTITY_MISMATCH"


def test_live_mode_is_blocked():
    orchestrator = make_orchestrator()
    record = make_signal_record()
    result = orchestrator.process_signal(record, trading_mode="LIVE", intent=buy_intent("10"))
    assert result.state == OrchestrationState.REJECTED
    assert result.reason_code == "LIVE_MODE_BLOCKED"


def test_unknown_mode_is_blocked():
    orchestrator = make_orchestrator()
    record = make_signal_record()
    result = orchestrator.process_signal(record, trading_mode="HACK", intent=buy_intent("10"))
    assert result.state == OrchestrationState.REJECTED
    assert result.reason_code == "LIVE_MODE_BLOCKED"


def test_missing_intent_fails_closed():
    # default resolver returns None (UnavailableOrderIntentResolver not injected)
    from alpha_algo_trading_engine.service import TradingOrchestrator
    from alpha_algo_risk_engine.service import RiskService

    orchestrator = TradingOrchestrator(risk_service=RiskService(provider=FakeRiskProvider()))
    record = make_signal_record()
    result = orchestrator.process_signal(record, trading_mode="PAPER")
    assert result.state == OrchestrationState.REJECTED
    assert result.reason_code == "INTENT_UNAVAILABLE"


def test_zero_quantity_fails_closed():
    orchestrator = make_orchestrator()
    record = make_signal_record()
    result = orchestrator.process_signal(record, trading_mode="PAPER", intent=buy_intent("0"))
    assert result.state == OrchestrationState.REJECTED
    assert result.reason_code == "INTENT_UNAVAILABLE"


def test_hold_never_creates_intent():
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(oms_port=port)
    signal = make_signal(action=SignalAction.HOLD)
    record = make_signal_record(signal)
    result = orchestrator.process_signal(record, trading_mode="PAPER", intent=buy_intent("10"))
    assert result.state == OrchestrationState.REJECTED
    assert result.reason_code == "ACTION_NOT_TRADABLE"
    assert port.intents == []


def test_risk_rejection_stops_flow():
    provider = FakeRiskProvider(snapshot=make_snapshot(global_halt_active=True))
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(provider=provider, oms_port=port)
    record = make_signal_record()
    result = orchestrator.process_signal(record, trading_mode="PAPER", intent=buy_intent("10"))
    assert result.state == OrchestrationState.REJECTED
    assert result.risk_decision is not None
    assert result.risk_decision.decision.value == "REJECTED"
    assert port.intents == []
    assert orchestrator.metrics.risk_calls == 1
    assert orchestrator.metrics.risk_rejections == 1


def test_persistence_failure_is_not_a_false_success():
    from alpha_algo_trading_engine.repository import TradingIntentRepository

    repo = TradingIntentRepository(
        FakeSessionFactory(commit_raises=RuntimeError("connection lost"))
    )
    port = RecordingOmsPort()
    orchestrator = make_orchestrator(repository=repo, oms_port=port)
    record = make_signal_record()
    result = orchestrator.process_signal(record, trading_mode="PAPER", intent=buy_intent("10"))
    assert result.state == OrchestrationState.FAILED
    assert result.reason_code == "PERSISTENCE_FAILED"
    # no handoff, no false success
    assert port.intents == []
    assert not result.handoff_delivered


def test_oms_port_failure_does_not_drop_intent():
    port = FailingOmsPort()
    orchestrator = make_orchestrator(oms_port=port)
    record = make_signal_record()
    result = orchestrator.process_signal(record, trading_mode="PAPER", intent=buy_intent("10"))
    # intent is still OMS_HANDOFF_READY + durable; only the handoff notify failed
    assert result.state == OrchestrationState.OMS_HANDOFF_READY
    assert result.handoff_delivered is False
    assert result.intent is not None
    assert orchestrator.metrics.oms_handoff_failures == 1


def test_hold_without_intent_still_reports_not_tradable():
    from alpha_algo_risk_engine.service import RiskService
    from alpha_algo_trading_engine.intent import UnavailableOrderIntentResolver
    from alpha_algo_trading_engine.service import TradingOrchestrator

    orchestrator = TradingOrchestrator(
        risk_service=RiskService(provider=FakeRiskProvider()),
        intent_resolver=UnavailableOrderIntentResolver(),
        oms_port=RecordingOmsPort(),
    )
    signal = make_signal(action=SignalAction.HOLD)
    record = make_signal_record(signal)
    result = orchestrator.process_signal(record, trading_mode="PAPER")
    assert result.state == OrchestrationState.REJECTED
    assert result.reason_code == "ACTION_NOT_TRADABLE"


def test_idempotency_cache_is_bounded():
    from alpha_algo_risk_engine.service import RiskService
    from alpha_algo_trading_engine.service import TradingOrchestrator

    orchestrator = TradingOrchestrator(
        risk_service=RiskService(provider=FakeRiskProvider()),
        intent_resolver=FixedIntentResolver(buy_intent()),
        oms_port=RecordingOmsPort(),
        idempotency_capacity=1,
    )
    a = make_signal_record()
    b = make_signal_record()
    assert orchestrator.process_signal(a, trading_mode="PAPER").state == OrchestrationState.OMS_HANDOFF_READY
    assert orchestrator.process_signal(b, trading_mode="PAPER").state == OrchestrationState.OMS_HANDOFF_READY
    # a was evicted (capacity=1); reprocessing a is NOT a duplicate
    assert orchestrator.process_signal(a, trading_mode="PAPER").state == OrchestrationState.OMS_HANDOFF_READY
    assert len(orchestrator._handed_off) <= 1
