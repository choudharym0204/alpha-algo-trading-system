"""Phase 7 deterministic orchestration-identity tests."""

from uuid import uuid4

from alpha_algo_trading_engine.identity import compute_orchestration_identity_key

from trading_test_support import buy_intent, make_buy_signal


def test_identity_is_deterministic():
    signal = make_buy_signal()
    intent = buy_intent("10")
    a = compute_orchestration_identity_key(signal, intent, "PAPER")
    b = compute_orchestration_identity_key(signal, intent, "PAPER")
    assert a == b
    assert len(a) == 64


def test_identity_differs_on_quantity():
    signal = make_buy_signal()
    assert compute_orchestration_identity_key(signal, buy_intent("10"), "PAPER") != (
        compute_orchestration_identity_key(signal, buy_intent("20"), "PAPER")
    )


def test_identity_differs_on_account():
    signal = make_buy_signal()
    assert compute_orchestration_identity_key(
        signal, buy_intent("10", account_id=uuid4()), "PAPER"
    ) != compute_orchestration_identity_key(
        signal, buy_intent("10", account_id=uuid4()), "PAPER"
    )


def test_identity_differs_on_order_type():
    signal = make_buy_signal()
    assert compute_orchestration_identity_key(signal, buy_intent("10", order_type="MARKET"), "PAPER") != (
        compute_orchestration_identity_key(signal, buy_intent("10", order_type="LIMIT"), "PAPER")
    )


def test_identity_differs_on_trading_mode():
    signal = make_buy_signal()
    intent = buy_intent("10")
    assert compute_orchestration_identity_key(signal, intent, "PAPER") != (
        compute_orchestration_identity_key(signal, intent, "BACKTEST")
    )


def test_identity_differs_on_signal_identity():
    s1 = make_buy_signal()
    s2 = make_buy_signal()
    intent = buy_intent("10")
    assert compute_orchestration_identity_key(s1, intent, "PAPER") != (
        compute_orchestration_identity_key(s2, intent, "PAPER")
    )


def test_identity_with_none_intent_is_stable():
    signal = make_buy_signal()
    a = compute_orchestration_identity_key(signal, None, "PAPER")
    b = compute_orchestration_identity_key(signal, None, "PAPER")
    assert a == b
