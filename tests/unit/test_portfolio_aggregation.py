"""Phase 12 — aggregation / exposure / market-value / funds tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from alpha_algo_portfolio_engine.contracts import PortfolioCompleteness, PortfolioStatus
from alpha_algo_portfolio_engine.engine import PortfolioEngine

from portfolio_test_support import (
    InMemoryPortfolioRepository,
    make_funds,
    make_inputs,
    make_position,
    make_price,
)


def make_engine(repo=None, max_age_seconds=None):
    return PortfolioEngine(
        repository=repo or InMemoryPortfolioRepository(),
        global_halt_active=lambda: False,
        max_age_seconds=max_age_seconds,
    )


def _now():
    return datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


def test_zero_positions():
    engine = make_engine()
    c = engine.compute(make_inputs(funds=make_funds()), now=_now())
    assert c.position_count == 0
    assert c.gross_exposure == Decimal("0")
    assert c.net_exposure == Decimal("0")
    assert c.long_exposure == Decimal("0")
    assert c.short_exposure == Decimal("0")
    assert c.market_value == Decimal("0")
    assert c.equity_value == Decimal("1000000.0000")  # cash only, no positions
    assert c.status == PortfolioStatus.READY
    assert c.completeness == PortfolioCompleteness.COMPLETE


def test_one_position_market_value_and_exposure():
    engine = make_engine()
    iid = uuid4()
    pos = make_position(instrument_id=iid, quantity=100)
    c = engine.compute(
        make_inputs(positions=(pos,), funds=make_funds(), prices={iid: make_price(iid, price="105")}),
        now=_now(),
    )
    assert c.position_count == 1
    assert c.market_value == Decimal("10500.0000")  # 100 * 105
    assert c.gross_exposure == Decimal("10500.0000")
    assert c.net_exposure == Decimal("10500.0000")
    assert c.long_exposure == Decimal("10500.0000")
    assert c.short_exposure == Decimal("0.0000")
    assert c.equity_value == Decimal("1010500.0000")  # cash 1,000,000 + 10,500


def test_multiple_positions_aggregate():
    engine = make_engine()
    i1, i2 = uuid4(), uuid4()
    p1 = make_position(instrument_id=i1, quantity=100)
    p2 = make_position(instrument_id=i2, quantity=50)
    c = engine.compute(
        make_inputs(
            positions=(p1, p2),
            funds=make_funds(),
            prices={i1: make_price(i1, price="100"), i2: make_price(i2, price="200")},
        ),
        now=_now(),
    )
    assert c.position_count == 2
    assert c.market_value == Decimal("20000.0000")  # 10000 + 10000
    assert c.gross_exposure == Decimal("20000.0000")
    assert c.net_exposure == Decimal("20000.0000")
    assert c.long_exposure == Decimal("20000.0000")


def test_exact_decimal_arithmetic():
    engine = make_engine()
    iid = uuid4()
    pos = make_position(instrument_id=iid, quantity=3)
    c = engine.compute(
        make_inputs(positions=(pos,), funds=make_funds(), prices={iid: make_price(iid, price="33.3333")}),
        now=_now(),
    )
    # 3 * 33.3333 = 99.9999
    assert c.market_value == Decimal("99.9999")


def test_strategy_breakdown():
    engine = make_engine()
    s1, s2 = uuid4(), uuid4()
    i1, i2, i3 = uuid4(), uuid4(), uuid4()
    p1 = make_position(instrument_id=i1, strategy_run_id=s1, quantity=100)
    p2 = make_position(instrument_id=i2, strategy_run_id=s1, quantity=50)
    p3 = make_position(instrument_id=i3, strategy_run_id=s2, quantity=200)
    c = engine.compute(
        make_inputs(
            positions=(p1, p2, p3),
            funds=make_funds(),
            prices={i1: make_price(i1, "100"), i2: make_price(i2, "100"), i3: make_price(i3, "50")},
        ),
        now=_now(),
    )
    by_strategy = {b.strategy_run_id: b for b in c.strategy_breakdown}
    assert by_strategy[s1].position_count == 2
    assert by_strategy[s1].gross_exposure == Decimal("15000.0000")  # 10000 + 5000
    assert by_strategy[s2].position_count == 1
    assert by_strategy[s2].gross_exposure == Decimal("10000.0000")  # 200*50


def test_funds_unavailable_not_zero():
    engine = make_engine()
    iid = uuid4()
    pos = make_position(instrument_id=iid, quantity=100)
    c = engine.compute(
        make_inputs(positions=(pos,), funds=None, prices={iid: make_price(iid, "100")}),
        now=_now(),
    )
    assert c.cash_balance is None
    assert c.funds_available is False
    assert c.equity_value is None  # cannot compute portfolio value without cash
    assert c.status == PortfolioStatus.DEGRADED
    assert c.completeness == PortfolioCompleteness.PARTIAL


def test_missing_price_degrades_and_flags():
    engine = make_engine()
    i1, i2 = uuid4(), uuid4()
    p1 = make_position(instrument_id=i1, quantity=100)
    p2 = make_position(instrument_id=i2, quantity=50)
    c = engine.compute(
        make_inputs(
            positions=(p1, p2),
            funds=make_funds(),
            prices={i1: make_price(i1, "100")},  # i2 missing
        ),
        now=_now(),
    )
    assert c.status == PortfolioStatus.DEGRADED
    assert c.completeness == PortfolioCompleteness.PARTIAL
    assert i2 in c.missing_instrument_ids
    assert c.market_value == Decimal("10000.0000")  # only priced position
    assert c.position_count == 2


def test_stale_price_degrades_and_flags():
    engine = make_engine(max_age_seconds=60)
    iid = uuid4()
    pos = make_position(instrument_id=iid, quantity=100)
    stale = make_price(iid, price="100", observed_at=_now() - timedelta(seconds=120))
    c = engine.compute(
        make_inputs(positions=(pos,), funds=make_funds(), prices={iid: stale}),
        now=_now(),
    )
    assert c.status == PortfolioStatus.DEGRADED
    assert iid in c.stale_instrument_ids
    # Stale price is still a real value -> included in market value.
    assert c.market_value == Decimal("10000.0000")


def test_future_dated_price_treated_as_stale():
    engine = make_engine(max_age_seconds=60)
    iid = uuid4()
    pos = make_position(instrument_id=iid, quantity=100)
    future = make_price(iid, price="100", observed_at=_now() + timedelta(seconds=10))
    c = engine.compute(
        make_inputs(positions=(pos,), funds=make_funds(), prices={iid: future}),
        now=_now(),
    )
    assert c.status == PortfolioStatus.DEGRADED
    assert iid in c.stale_instrument_ids


def test_closed_positions_not_counted():
    engine = make_engine()
    iid = uuid4()
    closed = make_position(instrument_id=iid, quantity=0, status="CLOSED")
    c = engine.compute(
        make_inputs(positions=(closed,), funds=make_funds(), prices={iid: make_price(iid, "100")}),
        now=_now(),
    )
    assert c.position_count == 0
    assert c.market_value == Decimal("0")
    assert c.gross_exposure == Decimal("0")


def test_margin_values_passed_through():
    engine = make_engine()
    c = engine.compute(make_inputs(funds=make_funds(available_margin="800000", used_margin="200000")), now=_now())
    assert c.available_margin == Decimal("800000.0000")
    assert c.used_margin == Decimal("200000.0000")
