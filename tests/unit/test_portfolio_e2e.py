"""Phase 12 — end-to-end test (Position → Portfolio → read-back)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from alpha_algo_portfolio_engine.adapters import (
    funds_from_broker_snapshot,
    position_input_from_snapshot,
)
from alpha_algo_portfolio_engine.contracts import PortfolioStatus
from alpha_algo_portfolio_engine.engine import PortfolioEngine

from portfolio_test_support import (
    InMemoryPortfolioRepository,
    make_funds,
    make_inputs,
    make_position,
    make_price,
)


class _FakePositionSnapshot:
    def __init__(self, position_id, instrument_id, strategy_run_id, quantity, average_price, status):
        self.position_id = position_id
        self.instrument_id = instrument_id
        self.strategy_run_id = strategy_run_id
        self.quantity = quantity
        self.average_price = average_price
        self.status = status


class _FakeFundsSnapshot:
    def __init__(self, available_cash, available_margin, used_margin, captured_at):
        self.available_cash = available_cash
        self.available_margin = available_margin
        self.used_margin = used_margin
        self.captured_at = captured_at


def _t():
    return datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


def test_position_to_portfolio_end_to_end():
    acc = uuid4()
    s1, s2 = uuid4(), uuid4()
    i1, i2 = uuid4(), uuid4()

    # Phase-11 authoritative positions (normalized through the boundary adapter).
    pos_a = _FakePositionSnapshot(uuid4(), i1, s1, 100, Decimal("95"), "OPEN")
    pos_b = _FakePositionSnapshot(uuid4(), i2, s2, 50, Decimal("180"), "OPEN")
    positions = (position_input_from_snapshot(pos_a), position_input_from_snapshot(pos_b))

    # Phase-10 funds snapshot (normalized through the boundary adapter).
    funds = funds_from_broker_snapshot(
        _FakeFundsSnapshot(Decimal("1000000"), Decimal("800000"), Decimal("200000"), _t())
    )

    prices = {i1: make_price(i1, "100"), i2: make_price(i2, "200")}
    inputs = make_inputs(account_id=acc, positions=positions, funds=funds, prices=prices)

    repo = InMemoryPortfolioRepository()
    engine = PortfolioEngine(repository=repo, global_halt_active=lambda: False)

    result = engine.snapshot(inputs, _t())

    assert result.status == PortfolioStatus.READY
    assert result.snapshot.position_count == 2
    assert result.snapshot.market_value == Decimal("20000.0000")  # 100*100 + 50*200
    assert result.snapshot.gross_exposure == Decimal("20000.0000")
    assert result.snapshot.net_exposure == Decimal("20000.0000")
    assert result.snapshot.cash_balance == Decimal("1000000.0000")
    assert result.snapshot.equity_value == Decimal("1020000.0000")

    # Read-back path produces the correct aggregate state.
    latest = engine.get_latest(account_id=acc, trading_mode="PAPER")
    assert latest.market_value == Decimal("20000.0000")
    assert latest.position_count == 2
    assert latest.equity_value == Decimal("1020000.0000")


def test_average_price_carried_but_not_used_for_exposure():
    # Exposure uses reference market price, not average entry price.
    engine = PortfolioEngine(repository=InMemoryPortfolioRepository(), global_halt_active=lambda: False)
    iid = uuid4()
    pos = make_position(instrument_id=iid, quantity=100, average_price="80")  # entry price
    c = engine.compute(
        make_inputs(positions=(pos,), funds=make_funds(), prices={iid: make_price(iid, "120")}),
        now=_t(),
    )
    # Exposure/market value use reference price (120), not average price (80).
    assert c.market_value == Decimal("12000.0000")
    assert c.positions[0].reference_price == Decimal("120.0000")
