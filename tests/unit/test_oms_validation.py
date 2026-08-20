"""Phase 8 OMS — intent-to-order validation tests."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from alpha_algo_oms.errors import OrderValidationError, TradingModeError
from alpha_algo_oms.validation import OrderSpec, validate_intent

from oms_test_support import expired_intent, make_intent


def _valid():
    return make_intent()


def _spec(intent, *, now=None, halt=False):
    return validate_intent(intent, now=now or datetime.now(UTC), global_halt_active=halt)


def test_valid_paper_intent_passes():
    spec = _spec(_valid(), halt=False)
    assert isinstance(spec, OrderSpec)
    assert spec.trading_mode == "PAPER"
    assert spec.side == "BUY"
    assert spec.quantity == 10
    assert spec.order_type == "MARKET"


def test_valid_backtest_intent_passes():
    i = make_intent(trading_mode="BACKTEST")
    spec = _spec(i, halt=False)
    assert spec.trading_mode == "BACKTEST"


def test_live_mode_is_blocked():
    i = make_intent(trading_mode="LIVE")
    with pytest.raises(TradingModeError):
        _spec(i, halt=False)


def test_unknown_mode_fails_closed():
    i = make_intent(trading_mode="HACK")
    with pytest.raises(TradingModeError):
        _spec(i, halt=False)


def test_global_halt_blocks_order():
    i = _valid()
    with pytest.raises(OrderValidationError):
        _spec(i, halt=True)


def test_default_halt_is_fail_closed():
    # no explicit global_halt_active -> defaults True -> blocked
    with pytest.raises(OrderValidationError):
        validate_intent(_valid(), now=datetime.now(UTC))


def test_expired_approval_is_rejected():
    i = expired_intent()
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_missing_orchestration_id_rejected():
    i = replace(_valid(), orchestration_id="")
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_none_orchestration_id_rejected():
    i = replace(_valid(), orchestration_id=None)
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_zero_quantity_rejected():
    i = make_intent(quantity="0")
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_negative_quantity_rejected():
    i = make_intent(quantity="-5")
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_fractional_quantity_rejected():
    i = replace(_valid(), quantity=Decimal("10.5"))
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_unsupported_action_rejected():
    i = replace(_valid(), action="HOLD")
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_unsupported_order_type_rejected():
    i = replace(_valid(), order_type="GTC")
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_missing_account_rejected():
    i = replace(_valid(), account_id=None)
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_missing_signal_rejected():
    i = replace(_valid(), signal_id=None)
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_missing_approval_rejected():
    i = replace(_valid(), approval_id=None)
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_naive_approval_expiry_rejected():
    i = replace(_valid(), approval_expires_at=datetime.now() + timedelta(seconds=30))
    with pytest.raises(OrderValidationError):
        _spec(i, halt=False)


def test_limit_order_preserves_limit_price():
    i = make_intent(order_type="LIMIT", limit_price=Decimal("99.5"))
    spec = _spec(i, halt=False)
    assert spec.order_type == "LIMIT"
    assert spec.limit_price == Decimal("99.5")


def test_quantity_is_whole_number_int():
    spec = _spec(make_intent(quantity="25"), halt=False)
    assert spec.quantity == 25
    assert isinstance(spec.quantity, int)
