"""Phase 6 — new configurable risk controls (drawdown, price, frequency, account,
execution timeout, retry safety)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from alpha_algo_contracts import RiskAssessmentRequest
from alpha_algo_risk_engine.engine import (
    AccountLimitRule,
    ExecutionTimeoutRule,
    MaximumDrawdownRule,
    OrderFrequencyRule,
    PriceDeviationRule,
    RetrySafetyRule,
    RiskEvaluationContext,
)

from risk_test_support import make_buy_signal


def _request():
    signal = make_buy_signal()
    return RiskAssessmentRequest(signal=signal, requested_at=datetime.now(UTC))


def _eval(rule, **ctx_kwargs):
    return rule.evaluate(_request(), RiskEvaluationContext(**ctx_kwargs))


# --- Maximum Drawdown -------------------------------------------------------


def test_drawdown_not_configured_passes():
    assert _eval(MaximumDrawdownRule(), max_drawdown=None).passed is True


def test_drawdown_within_limit_passes():
    r = _eval(MaximumDrawdownRule(), max_drawdown=Decimal("0.20"), current_drawdown=Decimal("0.05"))
    assert r.passed is True


def test_drawdown_breach_rejects():
    r = _eval(MaximumDrawdownRule(), max_drawdown=Decimal("0.20"), current_drawdown=Decimal("0.25"))
    assert r.passed is False
    assert r.reason_code == "DRAWDOWN_LIMIT_EXCEEDED"


def test_drawdown_missing_measure_fails_closed():
    r = _eval(MaximumDrawdownRule(), max_drawdown=Decimal("0.20"), current_drawdown=None)
    assert r.passed is False
    assert r.reason_code == "RISK_CONTEXT_MISSING"


# --- Price Deviation --------------------------------------------------------


def test_price_deviation_not_configured_passes():
    assert _eval(PriceDeviationRule(), max_price_deviation=None).passed is True


def test_price_deviation_within_limit_passes():
    r = _eval(
        PriceDeviationRule(),
        max_price_deviation=Decimal("0.05"),
        reference_price=Decimal("100"),
        current_price=Decimal("104"),
    )
    assert r.passed is True


def test_price_deviation_breach_rejects():
    r = _eval(
        PriceDeviationRule(),
        max_price_deviation=Decimal("0.05"),
        reference_price=Decimal("100"),
        current_price=Decimal("106"),
    )
    assert r.passed is False
    assert r.reason_code == "PRICE_DEVIATION_EXCEEDED"


def test_price_deviation_invalid_reference_rejects():
    r = _eval(
        PriceDeviationRule(),
        max_price_deviation=Decimal("0.05"),
        reference_price=Decimal("0"),
        current_price=Decimal("100"),
    )
    assert r.passed is False
    assert r.reason_code == "RISK_CONTEXT_INVALID"


def test_price_deviation_invalid_price_rejects():
    r = _eval(
        PriceDeviationRule(),
        max_price_deviation=Decimal("0.05"),
        reference_price=Decimal("100"),
        current_price=Decimal("0"),
    )
    assert r.passed is False
    assert r.reason_code == "PRICE_INVALID"


def test_price_deviation_missing_measure_fails_closed():
    r = _eval(PriceDeviationRule(), max_price_deviation=Decimal("0.05"), reference_price=Decimal("100"), current_price=None)
    assert r.passed is False
    assert r.reason_code == "RISK_CONTEXT_MISSING"


# --- Order Frequency --------------------------------------------------------


def test_order_frequency_not_configured_passes():
    assert _eval(OrderFrequencyRule(), max_orders_per_window=None).passed is True


def test_order_frequency_within_limit_passes():
    r = _eval(OrderFrequencyRule(), max_orders_per_window=10, recent_order_count=5)
    assert r.passed is True


def test_order_frequency_reached_rejects():
    r = _eval(OrderFrequencyRule(), max_orders_per_window=10, recent_order_count=10)
    assert r.passed is False
    assert r.reason_code == "ORDER_FREQUENCY_LIMIT_EXCEEDED"


def test_order_frequency_missing_measure_fails_closed():
    r = _eval(OrderFrequencyRule(), max_orders_per_window=10, recent_order_count=None)
    assert r.passed is False
    assert r.reason_code == "RISK_CONTEXT_MISSING"


# --- Account Limits ---------------------------------------------------------


def test_account_limits_not_configured_passes():
    assert _eval(AccountLimitRule()).passed is True


def test_account_order_quantity_limit():
    r = _eval(
        AccountLimitRule(),
        account_max_order_quantity=Decimal("50"),
        order_quantity=Decimal("100"),
    )
    assert r.passed is False
    assert r.reason_code == "ACCOUNT_ORDER_QUANTITY_LIMIT_EXCEEDED"


def test_account_position_limit():
    r = _eval(
        AccountLimitRule(),
        account_max_positions=5,
        open_positions_count=5,
    )
    assert r.passed is False
    assert r.reason_code == "ACCOUNT_POSITIONS_LIMIT_EXCEEDED"


def test_account_exposure_limit():
    r = _eval(
        AccountLimitRule(),
        account_max_exposure=Decimal("1000"),
        projected_exposure=Decimal("2000"),
    )
    assert r.passed is False
    assert r.reason_code == "ACCOUNT_EXPOSURE_LIMIT_EXCEEDED"


def test_account_loss_limit():
    r = _eval(
        AccountLimitRule(),
        account_max_loss=Decimal("1000"),
        account_daily_realized_pnl=Decimal("-1500"),
    )
    assert r.passed is False
    assert r.reason_code == "ACCOUNT_LOSS_LIMIT_EXCEEDED"


def test_account_order_rate_limit():
    r = _eval(
        AccountLimitRule(),
        account_max_order_rate=5,
        recent_order_count=5,
    )
    assert r.passed is False
    assert r.reason_code == "ACCOUNT_ORDER_RATE_EXCEEDED"


# --- Execution Timeout ------------------------------------------------------


def test_execution_timeout_not_configured_passes():
    assert _eval(ExecutionTimeoutRule(), max_unresolved_executions=None).passed is True


def test_execution_timeout_within_limit_passes():
    r = _eval(ExecutionTimeoutRule(), max_unresolved_executions=10, pending_execution_count=5)
    assert r.passed is True


def test_execution_timeout_reached_rejects():
    r = _eval(ExecutionTimeoutRule(), max_unresolved_executions=10, pending_execution_count=10)
    assert r.passed is False
    assert r.reason_code == "UNRESOLVED_EXECUTIONS_LIMIT_EXCEEDED"


# --- Retry Safety -----------------------------------------------------------


def test_retry_safety_not_configured_passes():
    assert _eval(RetrySafetyRule(), max_retries_per_signal=None).passed is True


def test_retry_safety_within_limit_passes():
    r = _eval(RetrySafetyRule(), max_retries_per_signal=5, retry_count=5)
    assert r.passed is True


def test_retry_safety_exceeded_rejects():
    r = _eval(RetrySafetyRule(), max_retries_per_signal=5, retry_count=6)
    assert r.passed is False
    assert r.reason_code == "MAX_RETRIES_EXCEEDED"
