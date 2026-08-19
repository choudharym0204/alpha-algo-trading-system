"""Phase 6 — approval binding + expiry/reuse validation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alpha_algo_contracts import RiskDecision, RiskDecisionResult
from alpha_algo_risk_engine.approval import (
    approval_is_usable,
    compute_approval_binding,
    compute_risk_identity_key,
)

from risk_test_support import make_buy_signal


def _now():
    return datetime.now(UTC)


def _intent(**kwargs):
    from alpha_algo_risk_engine.context import RiskOrderIntent

    return RiskOrderIntent(**kwargs)


def test_binding_is_stable_for_same_input():
    signal = make_buy_signal()
    assert compute_approval_binding(signal, None, "PAPER") == compute_approval_binding(
        signal, None, "PAPER"
    )


def test_binding_differs_on_quantity():
    signal = make_buy_signal()
    a = compute_approval_binding(signal, _intent(quantity=Decimal("10")), "PAPER")
    b = compute_approval_binding(signal, _intent(quantity=Decimal("20")), "PAPER")
    assert a != b


def test_binding_differs_on_account():
    signal = make_buy_signal()
    a = compute_approval_binding(signal, _intent(account_id=uuid4()), "PAPER")
    b = compute_approval_binding(signal, _intent(account_id=uuid4()), "PAPER")
    assert a != b


def test_binding_differs_on_signal():
    a = compute_approval_binding(make_buy_signal(), None, "PAPER")
    b = compute_approval_binding(make_buy_signal(), None, "PAPER")
    assert a != b


def test_identity_key_differs_on_trading_mode():
    signal = make_buy_signal()
    a = compute_risk_identity_key(signal, _intent(quantity=Decimal("10")), "PAPER")
    b = compute_risk_identity_key(signal, _intent(quantity=Decimal("10")), "BACKTEST")
    assert a != b


def test_identity_key_differs_on_order_type():
    signal = make_buy_signal()
    a = compute_risk_identity_key(signal, _intent(quantity=Decimal("10"), order_type="MARKET"), "PAPER")
    b = compute_risk_identity_key(signal, _intent(quantity=Decimal("10"), order_type="LIMIT"), "PAPER")
    assert a != b


def _decision(
    decision,
    *,
    evaluated_at=None,
    expires_at=None,
    binding_hash="abc",
    approval_id=None,
) -> RiskDecision:
    signal = make_buy_signal()
    evaluated_at = evaluated_at or _now()
    kwargs = dict(
        request_id=uuid4(),
        signal_id=signal.signal_id,
        strategy_id=signal.strategy_id,
        instrument_id=signal.instrument_id,
        decision=decision,
        reason_code="TEST",
        reason="test",
        rule_id="core.test",
        evaluated_at=evaluated_at,
        binding_hash=binding_hash,
    )
    if decision == RiskDecisionResult.APPROVED:
        kwargs["approval_id"] = approval_id or uuid4()
        kwargs["expires_at"] = (
            expires_at if expires_at is not None else evaluated_at + timedelta(seconds=30)
        )
    return RiskDecision(**kwargs)


def test_usable_approval():
    now = _now()
    d = _decision(RiskDecisionResult.APPROVED, evaluated_at=now, expires_at=now + timedelta(seconds=30))
    assert approval_is_usable(d, now, binding_hash="abc") is True


def test_usable_approval_requires_binding():
    now = _now()
    d = _decision(RiskDecisionResult.APPROVED, evaluated_at=now, expires_at=now + timedelta(seconds=30))
    # A caller that omits the request binding must not get "usable".
    assert approval_is_usable(d, now) is False


def test_unbound_approval_not_usable():
    now = _now()
    d = _decision(
        RiskDecisionResult.APPROVED,
        evaluated_at=now,
        expires_at=now + timedelta(seconds=30),
        binding_hash=None,
    )
    assert approval_is_usable(d, now, binding_hash="abc") is False


def test_expired_approval_not_usable():
    now = _now()
    d = _decision(
        RiskDecisionResult.APPROVED,
        evaluated_at=now - timedelta(seconds=60),
        expires_at=now - timedelta(seconds=30),
    )
    assert approval_is_usable(d, now, binding_hash="abc") is False


def test_rejected_not_usable():
    d = _decision(RiskDecisionResult.REJECTED)
    assert approval_is_usable(d, _now(), binding_hash="abc") is False


def test_binding_mismatch_not_usable():
    now = _now()
    d = _decision(
        RiskDecisionResult.APPROVED,
        evaluated_at=now,
        binding_hash="abc",
    )
    assert approval_is_usable(d, now, binding_hash="xyz") is False
    assert approval_is_usable(d, now, binding_hash="abc") is True
