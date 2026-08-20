"""Phase 13 — realized/net/unrealized accounting correctness tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from alpha_algo_pnl_engine.accounting import (
    costs_total,
    net_pnl,
    realized_pnl_long,
    unrealized_pnl_long,
)
from alpha_algo_pnl_engine.contracts import CostComponent
from alpha_algo_position_engine.arithmetic import weighted_average


def test_weighted_average_matches_spec_example():
    avg = weighted_average(previous_quantity=0, previous_average=None, fill_quantity=100, fill_price=Decimal("100"))
    avg = weighted_average(previous_quantity=100, previous_average=avg, fill_quantity=50, fill_price=Decimal("110"))
    # (100*100 + 50*110)/150 = 15500/150 = 103.3333
    assert avg == Decimal("103.3333")


def test_realized_pnl_spec_example_partial_close():
    avg = Decimal("103.3333")
    realized = realized_pnl_long(sell_price=Decimal("120"), average_cost=avg, closed_quantity=40)
    # (120 - 103.3333) * 40 = 16.6667 * 40 = 666.6680
    assert realized == Decimal("666.6680")


def test_single_profitable_trade():
    realized = realized_pnl_long(sell_price=Decimal("150"), average_cost=Decimal("100"), closed_quantity=100)
    assert realized == Decimal("5000.0000")


def test_single_losing_trade():
    realized = realized_pnl_long(sell_price=Decimal("80"), average_cost=Decimal("100"), closed_quantity=100)
    assert realized == Decimal("-2000.0000")


def test_break_even():
    realized = realized_pnl_long(sell_price=Decimal("100"), average_cost=Decimal("100"), closed_quantity=100)
    assert realized == Decimal("0.0000")


def test_net_pnl_subtracts_costs():
    assert net_pnl(gross=Decimal("5000.0000"), costs=Decimal("50.0000")) == Decimal("4950.0000")


def test_negative_pnl_is_valid_not_invalid():
    realized = realized_pnl_long(sell_price=Decimal("10"), average_cost=Decimal("100"), closed_quantity=5)
    assert realized == Decimal("-450.0000")  # negative P&L is a valid financial fact


def test_unrealized_pnl_long():
    u = unrealized_pnl_long(reference_price=Decimal("120"), average_cost=Decimal("100"), open_quantity=100)
    assert u == Decimal("2000.0000")


def test_unrealized_price_decrease_negative():
    u = unrealized_pnl_long(reference_price=Decimal("90"), average_cost=Decimal("100"), open_quantity=100)
    assert u == Decimal("-1000.0000")


def test_unrealized_zero_movement():
    u = unrealized_pnl_long(reference_price=Decimal("100"), average_cost=Decimal("100"), open_quantity=100)
    assert u == Decimal("0.0000")


def test_exact_decimal_no_float_rounding():
    # 1/3 style values must not drift from binary float artifacts
    realized = realized_pnl_long(sell_price=Decimal("10.3333"), average_cost=Decimal("10.0000"), closed_quantity=3)
    assert realized == Decimal("0.9999")  # 0.3333 * 3 exactly


def test_costs_total():
    costs = (CostComponent(Decimal("1.25")), CostComponent(Decimal("2.75"), kind="exchange"))
    assert costs_total(costs) == Decimal("4.0000")


def test_cost_amount_must_be_non_negative():
    with pytest.raises(ValueError):
        CostComponent(Decimal("-1"))


def test_realized_rejects_non_positive_quantity():
    with pytest.raises(ValueError):
        realized_pnl_long(sell_price=Decimal("120"), average_cost=Decimal("100"), closed_quantity=0)


def test_fees_without_pnl():
    # Gross 0, costs > 0 => net negative (fees are not discarded).
    gross = realized_pnl_long(sell_price=Decimal("100"), average_cost=Decimal("100"), closed_quantity=10)
    assert gross == Decimal("0.0000")
    net = net_pnl(gross=gross, costs=Decimal("25.0000"))
    assert net == Decimal("-25.0000")
