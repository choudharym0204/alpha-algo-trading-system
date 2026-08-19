"""Shared helpers for Phase 7 trading-orchestrator tests (not a test module)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from alpha_algo_contracts import RiskDecision, RiskDecisionResult
from alpha_algo_risk_engine.context import RiskOrderIntent
from alpha_algo_risk_engine.service import RiskService
from alpha_algo_signal_engine.identity import compute_signal_identity_key
from alpha_algo_signal_engine.service import SignalRecord
from alpha_algo_signal_engine.state import SignalState
from alpha_algo_trading_engine.oms_port import HandoffResult
from alpha_algo_trading_engine.service import TradingOrchestrator

from risk_test_support import (  # noqa: F401
    FakeRiskProvider,
    FakeSessionFactory,
    healthy_account,
    make_buy_signal,
    make_snapshot,
)
from signal_test_support import make_signal  # noqa: F401


class FixedIntentResolver:
    def __init__(self, intent: RiskOrderIntent | None) -> None:
        self.intent = intent

    def resolve(self, signal, trading_mode: str) -> RiskOrderIntent | None:
        return self.intent


class RecordingOmsPort:
    def __init__(self) -> None:
        self.intents = []

    def handoff(self, intent):
        self.intents.append(intent)
        return HandoffResult(delivered=True)


class FailingOmsPort:
    def __init__(self, reason: str = "oms unavailable") -> None:
        self.reason = reason
        self.calls = 0

    def handoff(self, intent):
        self.calls += 1
        return HandoffResult(delivered=False, reason=self.reason)


class FakeDecisionRiskService:
    """Returns a fixed RiskDecision (for approval-expiry / binding-mismatch tests)."""

    def __init__(self, decision: RiskDecision) -> None:
        self.decision = decision

    def evaluate(self, signal, *, intent=None, trading_mode="PAPER"):
        return SimpleNamespace(decision=self.decision)


def buy_intent(
    quantity: str = "10",
    account_id: UUID | None = None,
    order_type: str = "MARKET",
) -> RiskOrderIntent:
    return RiskOrderIntent(
        quantity=Decimal(quantity), account_id=account_id, order_type=order_type
    )


def make_signal_record(signal=None, *, state: SignalState = SignalState.PERSISTED) -> SignalRecord:
    signal = signal or make_buy_signal()
    return SignalRecord(
        signal=signal,
        record_id=uuid4(),
        identity_key=compute_signal_identity_key(signal),
        state=state,
    )


def make_orchestrator(
    *,
    provider=None,
    repository=None,
    intent_resolver=None,
    oms_port=None,
    clock=None,
    risk_service=None,
) -> TradingOrchestrator:
    risk = risk_service or RiskService(
        provider=provider or FakeRiskProvider(),
        clock=clock,
    )
    return TradingOrchestrator(
        risk_service=risk,
        intent_resolver=intent_resolver or FixedIntentResolver(buy_intent()),
        oms_port=oms_port or RecordingOmsPort(),
        repository=repository,
        clock=clock,
    )


def make_approved_decision(
    signal,
    *,
    binding_hash: str,
    evaluated_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> RiskDecision:
    evaluated_at = evaluated_at or datetime.now(UTC)
    return RiskDecision(
        decision_id=uuid4(),
        request_id=uuid4(),
        signal_id=signal.signal_id,
        strategy_id=signal.strategy_id,
        instrument_id=signal.instrument_id,
        decision=RiskDecisionResult.APPROVED,
        reason_code="ALL_RULES_PASSED",
        reason="ok",
        rule_id="core.risk-rule-engine",
        evaluated_at=evaluated_at,
        approval_id=uuid4(),
        expires_at=expires_at or (evaluated_at + timedelta(seconds=30)),
        binding_hash=binding_hash,
    )
