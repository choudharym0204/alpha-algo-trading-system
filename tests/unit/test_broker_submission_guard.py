from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from alpha_algo_contracts import RiskDecision, RiskDecisionResult
from alpha_algo_execution_engine import (
    BrokerSubmissionGuard,
    InvalidOrderTransition,
    OrderLifecycle,
    OrderState,
    RiskApprovalRequired,
)


FIXED_NOW = datetime(2026, 1, 1, 9, 15, tzinfo=UTC)
SIGNAL_ID = UUID("10000000-0000-0000-0000-000000000001")
STRATEGY_ID = UUID("20000000-0000-0000-0000-000000000001")
INSTRUMENT_ID = UUID("30000000-0000-0000-0000-000000000001")


def _lifecycle_ready_for_submission() -> OrderLifecycle:
    return OrderLifecycle(order_id=uuid4()).transition_to(
        OrderState.INTERNAL_ORDER_CREATED,
        occurred_at=FIXED_NOW,
        reason="internal order created",
    )


def _approved_decision(*, expires_at=None, signal_id=SIGNAL_ID) -> RiskDecision:
    return RiskDecision(
        decision_id=UUID("40000000-0000-0000-0000-000000000001"),
        request_id=UUID("50000000-0000-0000-0000-000000000001"),
        signal_id=signal_id,
        strategy_id=STRATEGY_ID,
        instrument_id=INSTRUMENT_ID,
        decision=RiskDecisionResult.APPROVED,
        reason_code="ALL_RULES_PASSED",
        reason="all configured risk rules passed",
        rule_id="core.risk-rule-engine",
        evaluated_at=FIXED_NOW,
        approval_id=UUID("60000000-0000-0000-0000-000000000001"),
        expires_at=expires_at or FIXED_NOW + timedelta(seconds=30),
    )


def _rejected_decision() -> RiskDecision:
    return RiskDecision(
        decision_id=UUID("40000000-0000-0000-0000-000000000002"),
        request_id=UUID("50000000-0000-0000-0000-000000000002"),
        signal_id=SIGNAL_ID,
        strategy_id=STRATEGY_ID,
        instrument_id=INSTRUMENT_ID,
        decision=RiskDecisionResult.REJECTED,
        reason_code="LIMIT_EXCEEDED",
        reason="quantity limit exceeded",
        rule_id="core.quantity-limit",
        evaluated_at=FIXED_NOW,
    )


def test_submission_guard_accepts_valid_unexpired_matching_risk_approval() -> None:
    guard = BrokerSubmissionGuard()
    lifecycle = _lifecycle_ready_for_submission()

    next_lifecycle, intent = guard.request_submission(
        lifecycle=lifecycle,
        risk_decision=_approved_decision(),
        signal_id=SIGNAL_ID,
        strategy_id=STRATEGY_ID,
        instrument_id=INSTRUMENT_ID,
        requested_at=FIXED_NOW + timedelta(seconds=1),
        metadata={"client_order_id": "client-1"},
    )

    assert next_lifecycle.state == OrderState.SUBMISSION_REQUESTED
    assert intent.risk_approval_id == UUID("60000000-0000-0000-0000-000000000001")
    assert intent.metadata["risk_decision_id"] == "40000000-0000-0000-0000-000000000001"
    assert next_lifecycle.transitions[-1].metadata["risk_approval_id"] == str(
        intent.risk_approval_id
    )


def test_submission_guard_rejects_missing_risk_decision() -> None:
    guard = BrokerSubmissionGuard()

    with pytest.raises(RiskApprovalRequired, match="required"):
        guard.request_submission(
            lifecycle=_lifecycle_ready_for_submission(),
            risk_decision=None,
            signal_id=SIGNAL_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=INSTRUMENT_ID,
            requested_at=FIXED_NOW,
        )


def test_submission_guard_rejects_rejected_risk_decision() -> None:
    guard = BrokerSubmissionGuard()

    with pytest.raises(RiskApprovalRequired, match="not approved"):
        guard.request_submission(
            lifecycle=_lifecycle_ready_for_submission(),
            risk_decision=_rejected_decision(),
            signal_id=SIGNAL_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=INSTRUMENT_ID,
            requested_at=FIXED_NOW,
        )


def test_submission_guard_rejects_expired_risk_approval() -> None:
    guard = BrokerSubmissionGuard()

    with pytest.raises(RiskApprovalRequired, match="expired"):
        guard.request_submission(
            lifecycle=_lifecycle_ready_for_submission(),
            risk_decision=_approved_decision(expires_at=FIXED_NOW + timedelta(seconds=5)),
            signal_id=SIGNAL_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=INSTRUMENT_ID,
            requested_at=FIXED_NOW + timedelta(seconds=5),
        )


def test_submission_guard_rejects_mismatched_signal_identity() -> None:
    guard = BrokerSubmissionGuard()

    with pytest.raises(RiskApprovalRequired, match="signal_id"):
        guard.request_submission(
            lifecycle=_lifecycle_ready_for_submission(),
            risk_decision=_approved_decision(signal_id=uuid4()),
            signal_id=SIGNAL_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=INSTRUMENT_ID,
            requested_at=FIXED_NOW,
        )


def test_submission_guard_rejects_invalid_lifecycle_state() -> None:
    guard = BrokerSubmissionGuard()

    with pytest.raises(InvalidOrderTransition):
        guard.request_submission(
            lifecycle=OrderLifecycle(order_id=uuid4()),
            risk_decision=_approved_decision(),
            signal_id=SIGNAL_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=INSTRUMENT_ID,
            requested_at=FIXED_NOW,
        )


def test_submission_guard_requires_timezone_aware_requested_at() -> None:
    guard = BrokerSubmissionGuard()

    with pytest.raises(ValueError, match="timezone-aware"):
        guard.request_submission(
            lifecycle=_lifecycle_ready_for_submission(),
            risk_decision=_approved_decision(),
            signal_id=SIGNAL_ID,
            strategy_id=STRATEGY_ID,
            instrument_id=INSTRUMENT_ID,
            requested_at=datetime(2026, 1, 1),
        )


def test_submission_guard_exposes_no_real_broker_submission_method() -> None:
    guard = BrokerSubmissionGuard()

    forbidden_names = {
        "broker",
        "broker_credentials",
        "credentials",
        "place_order",
        "submit_order",
        "send_order",
        "execute_order",
    }

    assert forbidden_names.isdisjoint(dir(guard))
