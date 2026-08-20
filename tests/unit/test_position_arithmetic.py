"""Phase 11 — pure financial arithmetic tests (weighted average, buy/sell)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from alpha_algo_position_engine.arithmetic import (
    apply_buy,
    apply_sell,
    round_price,
    weighted_average,
)
from alpha_algo_position_engine.contracts import PositionStatus


def _t():
    return datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


def test_weighted_average_single_fill():
    assert weighted_average(previous_quantity=0, previous_average=None, fill_quantity=100, fill_price=Decimal("100")) == Decimal("100.0000")


def test_weighted_average_accumulation():
    # (100*100 + 50*110) / 150 = 103.3333...
    avg = weighted_average(previous_quantity=100, previous_average=Decimal("100"), fill_quantity=50, fill_price=Decimal("110"))
    assert avg == Decimal("103.3333")


def test_weighted_average_high_precision():
    # (1 * 10.001 + 1 * 10.003) / 2 = 10.002
    avg = weighted_average(previous_quantity=1, previous_average=Decimal("10.001"), fill_quantity=1, fill_price=Decimal("10.003"))
    assert avg == Decimal("10.0020")


def test_round_price_quantizes():
    assert round_price(Decimal("103.33334")) == Decimal("103.3333")
    assert round_price(Decimal("100.00004")) == Decimal("100.0000")


def test_apply_buy_opens_long():
    delta = apply_buy(quantity=0, average_price=None, opened_at=None, closed_at=None, fill_quantity=100, fill_price=Decimal("100"), occurred_at=_t())
    assert delta.quantity == 100
    assert delta.average_price == Decimal("100.0000")
    assert delta.status == PositionStatus.OPEN
    assert delta.event_type == "POSITION_OPENED"
    assert delta.opened_at == _t()


def test_apply_buy_increases_long():
    delta = apply_buy(quantity=100, average_price=Decimal("100"), opened_at=_t(), closed_at=None, fill_quantity=50, fill_price=Decimal("110"), occurred_at=_t())
    assert delta.quantity == 150
    assert delta.average_price == Decimal("103.3333")
    assert delta.event_type == "POSITION_INCREASED"


def test_apply_sell_partial_close_preserves_average():
    delta = apply_sell(quantity=100, average_price=Decimal("100"), opened_at=_t(), closed_at=None, fill_quantity=40, fill_price=Decimal("120"), occurred_at=_t())
    assert delta.quantity == 60
    assert delta.average_price == Decimal("100")  # entry unchanged
    assert delta.status == PositionStatus.OPEN
    assert delta.event_type == "POSITION_DECREASED"


def test_apply_sell_full_close():
    delta = apply_sell(quantity=60, average_price=Decimal("100"), opened_at=_t(), closed_at=None, fill_quantity=60, fill_price=Decimal("120"), occurred_at=_t())
    assert delta.quantity == 0
    assert delta.average_price is None
    assert delta.status == PositionStatus.CLOSED
    assert delta.event_type == "POSITION_CLOSED"
    assert delta.closed_at == _t()


def test_apply_sell_over_close_rejected():
    with pytest.raises(ValueError):
        apply_sell(quantity=50, average_price=Decimal("100"), opened_at=_t(), closed_at=None, fill_quantity=80, fill_price=Decimal("120"), occurred_at=_t())
