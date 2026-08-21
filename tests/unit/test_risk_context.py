"""Phase 6 — risk context builder + validator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from alpha_algo_contracts import SignalAction
from alpha_algo_risk_engine.context import (
    RiskContextBuilder,
    RiskContextUnavailable,
    RiskContextValidator,
    RiskOrderIntent,
)
from alpha_algo_risk_engine.engine import RiskTradingMode

from risk_test_support import (
    healthy_account,
    healthy_market,
    healthy_positions,
    make_buy_signal,
    make_snapshot,
)


def _builder(clock=None):
    return RiskContextBuilder(clock=clock or (lambda: datetime.now(UTC)))


def test_build_valid_context():
    signal = make_buy_signal()
    snap = make_snapshot()
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("10")), snap)
    assert ctx.trading_mode == RiskTradingMode.PAPER
    assert ctx.global_halt_active is False
    assert ctx.order_quantity == Decimal("10")
    assert ctx.projected_position_quantity == Decimal("10")
    assert ctx.projected_exposure == Decimal("1000")  # 0 + 10 * 100
    assert ctx.required_margin == Decimal("1000")
    assert ctx.equity_value == Decimal("100000")
    assert ctx.current_drawdown == Decimal("0")


def test_unavailable_state_fails_closed():
    signal = make_buy_signal()
    snap = make_snapshot(state_available=False)
    with pytest.raises(RiskContextUnavailable):
        _builder().build(signal, RiskOrderIntent(quantity=Decimal("10")), snap)


def test_stale_snapshot_fails_closed():
    now = datetime.now(UTC)
    signal = make_buy_signal()
    snap = make_snapshot(
        taken_at=now - timedelta(seconds=30), max_age=timedelta(seconds=5)
    )
    with pytest.raises(RiskContextUnavailable):
        _builder(clock=lambda: now).build(signal, RiskOrderIntent(quantity=Decimal("10")), snap)


def test_projected_position_includes_reserved():
    signal = make_buy_signal()
    snap = make_snapshot(
        positions=healthy_positions(
            position_quantity=Decimal("90"),
            projected_position_quantity=None,
            reserved_quantity=Decimal("10"),
        )
    )
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("10")), snap)
    assert ctx.projected_position_quantity == Decimal("110")  # 90 + 10 reserved + 10 intent


def test_projected_position_uses_authoritative_value():
    signal = make_buy_signal()
    snap = make_snapshot(positions=healthy_positions(projected_position_quantity=Decimal("95")))
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("10")), snap)
    assert ctx.projected_position_quantity == Decimal("105")  # 95 + 10


def test_sell_reduces_projected_position():

    signal = make_buy_signal()
    signal = signal.model_copy(update={"action": SignalAction.SELL})
    snap = make_snapshot(positions=healthy_positions(position_quantity=Decimal("50"), projected_position_quantity=None))
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("20")), snap)
    assert ctx.projected_position_quantity == Decimal("30")  # 50 - 20


def test_drawdown_derived_from_high_water_mark():
    signal = make_buy_signal()
    snap = make_snapshot(
        account=healthy_account(equity=Decimal("90000"), high_water_mark=Decimal("100000"), current_drawdown=None)
    )
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("10")), snap)
    assert ctx.current_drawdown == Decimal("0.10")


def test_missing_exposure_stays_none():
    signal = make_buy_signal()
    snap = make_snapshot(positions=healthy_positions(exposure=None))
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("10")), snap)
    assert ctx.projected_exposure is None


def test_validator_accepts_valid_context():
    signal = make_buy_signal()
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("10")), make_snapshot())
    assert RiskContextValidator().validate(ctx) == []


def test_validator_rejects_negative_equity():
    signal = make_buy_signal()
    snap = make_snapshot(account=healthy_account(equity=Decimal("-1")))
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("10")), snap)
    problems = RiskContextValidator().validate(ctx)
    assert any("equity_value" in p for p in problems)


def test_drawdown_clamped_at_new_equity_high():
    signal = make_buy_signal()
    snap = make_snapshot(
        account=healthy_account(
            equity=Decimal("110000"), high_water_mark=Decimal("100000"), current_drawdown=None
        )
    )
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("10")), snap)
    assert ctx.current_drawdown == Decimal("0")


def test_exposure_fails_closed_when_price_missing():
    signal = make_buy_signal()
    snap = make_snapshot(
        positions=healthy_positions(exposure=Decimal("1000")),
        market=healthy_market(current_price=None),
    )
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("10")), snap)
    assert ctx.projected_exposure is None


def test_account_mismatch_fails_closed():
    from uuid import uuid4

    signal = make_buy_signal()
    snap = make_snapshot(account=healthy_account(account_id=uuid4()))
    with pytest.raises(RiskContextUnavailable):
        _builder().build(
            signal, RiskOrderIntent(quantity=Decimal("10"), account_id=uuid4()), snap
        )


def test_trading_mode_mismatch_fails_closed():
    signal = make_buy_signal()
    snap = make_snapshot(trading_mode="LIVE")
    with pytest.raises(RiskContextUnavailable):
        _builder().build(signal, RiskOrderIntent(quantity=Decimal("10")), snap, trading_mode="PAPER")


def test_exit_reduces_position():
    signal = make_buy_signal().model_copy(update={"action": SignalAction.EXIT})
    snap = make_snapshot(
        positions=healthy_positions(position_quantity=Decimal("50"), projected_position_quantity=None)
    )
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("20")), snap)
    assert ctx.projected_position_quantity == Decimal("30")


def test_hold_carries_no_quantity():
    signal = make_buy_signal().model_copy(update={"action": SignalAction.HOLD})
    snap = make_snapshot(
        positions=healthy_positions(position_quantity=Decimal("50"), projected_position_quantity=None)
    )
    ctx = _builder().build(signal, RiskOrderIntent(quantity=Decimal("20")), snap)
    assert ctx.order_quantity is None
    assert ctx.projected_position_quantity == Decimal("50")


def test_action_sign_unknown_raises():
    from alpha_algo_risk_engine.context import _action_sign

    with pytest.raises(RiskContextUnavailable):
        _action_sign("NOT_A_REAL_ACTION")
