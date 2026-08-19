from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from alpha_algo_contracts import (
    RiskAssessmentRequest,
    RiskDecision,
    RiskDecisionResult,
    SignalAction,
    StrategySignal,
)


def _signal() -> StrategySignal:
    return StrategySignal(
        signal_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version="1.0.0",
        strategy_config_hash="sha256:config",
        instrument_id=uuid4(),
        action=SignalAction.BUY,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        confidence=Decimal("0.75"),
        reason="indicator threshold crossed",
    )


def _approved_decision(*, evaluated_at=None, expires_at=None) -> RiskDecision:
    signal = _signal()
    evaluated = evaluated_at or datetime(2026, 1, 1, tzinfo=UTC)
    return RiskDecision(
        request_id=uuid4(),
        signal_id=signal.signal_id,
        strategy_id=signal.strategy_id,
        instrument_id=signal.instrument_id,
        decision=RiskDecisionResult.APPROVED,
        reason_code="WITHIN_LIMITS",
        reason="signal passed configured risk limits",
        rule_id="core.max-exposure",
        evaluated_at=evaluated,
        approval_id=uuid4(),
        expires_at=expires_at or evaluated + timedelta(seconds=30),
    )


def test_risk_assessment_request_wraps_signal_with_request_timestamp() -> None:
    signal = _signal()

    request = RiskAssessmentRequest(
        signal=signal,
        requested_at=datetime(2026, 1, 1, tzinfo=UTC),
        metadata={"source": "unit-test"},
    )

    assert request.signal == signal
    assert request.metadata == {"source": "unit-test"}


def test_risk_assessment_request_rejects_naive_requested_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        RiskAssessmentRequest(signal=_signal(), requested_at=datetime(2026, 1, 1))


def test_approved_risk_decision_requires_unexpired_approval() -> None:
    evaluated_at = datetime(2026, 1, 1, tzinfo=UTC)
    decision = _approved_decision(evaluated_at=evaluated_at)

    assert decision.is_valid_approval_at(evaluated_at + timedelta(seconds=1)) is True
    assert decision.is_valid_approval_at(evaluated_at + timedelta(seconds=30)) is False


def test_approved_risk_decision_requires_approval_id() -> None:
    signal = _signal()

    with pytest.raises(ValidationError, match="approval_id"):
        RiskDecision(
            request_id=uuid4(),
            signal_id=signal.signal_id,
            strategy_id=signal.strategy_id,
            instrument_id=signal.instrument_id,
            decision=RiskDecisionResult.APPROVED,
            reason_code="WITHIN_LIMITS",
            reason="signal passed configured risk limits",
            rule_id="core.max-exposure",
            evaluated_at=datetime(2026, 1, 1, tzinfo=UTC),
            expires_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=30),
        )


def test_approved_risk_decision_rejects_expired_approval() -> None:
    evaluated_at = datetime(2026, 1, 1, tzinfo=UTC)

    with pytest.raises(ValidationError, match="expires_at"):
        _approved_decision(
            evaluated_at=evaluated_at,
            expires_at=evaluated_at - timedelta(seconds=1),
        )


def test_rejected_risk_decision_cannot_carry_approval_fields() -> None:
    signal = _signal()

    with pytest.raises(ValidationError, match="approval fields"):
        RiskDecision(
            request_id=uuid4(),
            signal_id=signal.signal_id,
            strategy_id=signal.strategy_id,
            instrument_id=signal.instrument_id,
            decision=RiskDecisionResult.REJECTED,
            reason_code="STALE_MARKET_DATA",
            reason="latest tick is stale",
            rule_id="core.market-data-freshness",
            evaluated_at=datetime(2026, 1, 1, tzinfo=UTC),
            approval_id=uuid4(),
            expires_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=30),
        )


def test_rejected_risk_decision_is_never_valid_approval() -> None:
    signal = _signal()
    decision = RiskDecision(
        request_id=uuid4(),
        signal_id=signal.signal_id,
        strategy_id=signal.strategy_id,
        instrument_id=signal.instrument_id,
        decision=RiskDecisionResult.REJECTED,
        reason_code="LIMIT_EXCEEDED",
        reason="quantity limit exceeded",
        rule_id="core.quantity-limit",
        evaluated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert decision.is_valid_approval_at(datetime(2026, 1, 1, tzinfo=UTC)) is False


def test_risk_decision_has_no_broker_or_order_submission_fields() -> None:
    contract_fields = set(RiskDecision.model_fields)

    assert {
        "broker_credentials",
        "credentials",
        "broker_order_id",
        "submit_order",
        "place_order",
    }.isdisjoint(contract_fields)
