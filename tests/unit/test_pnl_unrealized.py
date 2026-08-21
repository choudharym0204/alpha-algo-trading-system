"""Phase 13 — unrealized P&L (mark-to-market + freshness) tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from alpha_algo_pnl_engine.contracts import PnlStatus, PriceState
from alpha_algo_pnl_engine.engine import PnlEngine

from pnl_test_support import InMemoryPnlRepository, make_position, make_price


def make_engine(max_age_seconds=None):
    return PnlEngine(
        repository=InMemoryPnlRepository(),
        global_halt_active=lambda: False,
        max_age_seconds=max_age_seconds,
    )


def _now():
    return datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


def test_open_position_fresh_price():
    engine = make_engine()
    pos = make_position(quantity=100, average_price="100")
    price = make_price(pos.instrument_id, "120", _now())
    u = engine.mark_to_market(position=pos, price=price, now=_now())
    assert u.unrealized_pnl == Decimal("2000.0000")
    assert u.status == PnlStatus.READY
    assert u.price_state == PriceState.FRESH


def test_open_position_price_increase_and_decrease():
    engine = make_engine()
    pos = make_position(quantity=100, average_price="100")
    up = engine.mark_to_market(position=pos, price=make_price(pos.instrument_id, "130", _now()), now=_now())
    down = engine.mark_to_market(position=pos, price=make_price(pos.instrument_id, "90", _now()), now=_now())
    assert up.unrealized_pnl == Decimal("3000.0000")
    assert down.unrealized_pnl == Decimal("-1000.0000")


def test_missing_price_is_unavailable_not_zero():
    engine = make_engine()
    pos = make_position(quantity=100, average_price="100")
    u = engine.mark_to_market(position=pos, price=None, now=_now())
    assert u.unrealized_pnl is None
    assert u.status == PnlStatus.UNAVAILABLE
    assert u.price_state == PriceState.MISSING


def test_stale_price_is_degraded():
    engine = make_engine(max_age_seconds=60)
    pos = make_position(quantity=100, average_price="100")
    stale = make_price(pos.instrument_id, "120", _now() - timedelta(seconds=120))
    u = engine.mark_to_market(position=pos, price=stale, now=_now())
    assert u.status == PnlStatus.DEGRADED
    assert u.price_state == PriceState.STALE
    assert u.unrealized_pnl == Decimal("2000.0000")  # value present but flagged stale


def test_future_price_is_degraded():
    engine = make_engine(max_age_seconds=60)
    pos = make_position(quantity=100, average_price="100")
    future = make_price(pos.instrument_id, "120", _now() + timedelta(seconds=10))
    u = engine.mark_to_market(position=pos, price=future, now=_now())
    assert u.status == PnlStatus.DEGRADED
    assert u.price_state == PriceState.STALE


def test_invalid_non_positive_price_is_missing():
    engine = make_engine()
    pos = make_position(quantity=100, average_price="100")
    u = engine.mark_to_market(position=pos, price=make_price(pos.instrument_id, "0", _now()), now=_now())
    assert u.unrealized_pnl is None
    assert u.status == PnlStatus.UNAVAILABLE


def test_flat_position_unrealized_is_zero():
    engine = make_engine()
    pos = make_position(quantity=0, average_price=None, status="CLOSED")
    u = engine.mark_to_market(position=pos, price=None, now=_now())
    assert u.unrealized_pnl == Decimal("0.0000")
    assert u.status == PnlStatus.READY


def test_no_average_cost_is_unavailable():
    engine = make_engine()
    pos = make_position(quantity=100, average_price=None)
    u = engine.mark_to_market(position=pos, price=make_price(pos.instrument_id, "120", _now()), now=_now())
    assert u.unrealized_pnl is None
    assert u.status == PnlStatus.UNAVAILABLE
