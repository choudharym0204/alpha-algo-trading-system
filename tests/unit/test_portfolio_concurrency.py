"""Phase 12 — concurrency tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from alpha_algo_portfolio_engine.engine import PortfolioEngine

from portfolio_test_support import (
    InMemoryPortfolioRepository,
    make_funds,
    make_inputs,
    make_position,
    make_price,
)


def make_engine(repo):
    return PortfolioEngine(repository=repo, global_halt_active=lambda: False)


def _t():
    return datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


def _priced_inputs(*, account_id=None, quantity=100, price="100"):
    iid = uuid4()
    pos = make_position(instrument_id=iid, quantity=quantity)
    return make_inputs(
        account_id=account_id,
        positions=(pos,),
        funds=make_funds(),
        prices={iid: make_price(iid, price=price)},
    )


def test_concurrent_same_portfolio_snapshot_is_idempotent():
    repo = InMemoryPortfolioRepository()
    engine = make_engine(repo)
    acc = uuid4()
    inputs = _priced_inputs(account_id=acc)

    def work(_):
        return engine.snapshot(inputs, _t())

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(work, range(16)))

    # Exactly one authoritative snapshot survives (unique constraint).
    assert len(repo.snapshots) == 1
    duplicates = [r for r in results if r.duplicate]
    successes = [r for r in results if not r.duplicate]
    assert len(successes) == 1
    assert len(duplicates) == 15
    assert successes[0].snapshot.market_value == Decimal("10000.0000")


def test_concurrent_different_portfolios_do_not_collide():
    repo = InMemoryPortfolioRepository()
    engine = make_engine(repo)
    accs = [uuid4() for _ in range(8)]

    def work(acc):
        return engine.snapshot(_priced_inputs(account_id=acc), _t())

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(work, accs))

    assert len(repo.snapshots) == 8
    for acc in accs:
        assert engine.get_latest(account_id=acc, trading_mode="PAPER").account_id == acc


def test_concurrent_recalculation_produces_consistent_aggregates():
    repo = InMemoryPortfolioRepository()
    engine = make_engine(repo)
    acc = uuid4()
    i1, i2 = uuid4(), uuid4()
    p1 = make_position(instrument_id=i1, quantity=100)
    p2 = make_position(instrument_id=i2, quantity=50)
    inputs = make_inputs(
        account_id=acc,
        positions=(p1, p2),
        funds=make_funds(),
        prices={i1: make_price(i1, "100"), i2: make_price(i2, "200")},
    )

    def work(_):
        return engine.compute(inputs, now=_t())

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(work, range(32)))

    for c in results:
        assert c.market_value == Decimal("20000.0000")
        assert c.gross_exposure == Decimal("20000.0000")
        assert c.position_count == 2


def test_restart_then_recalculation_consistent():
    repo = InMemoryPortfolioRepository()
    acc = uuid4()
    inputs = _priced_inputs(account_id=acc, quantity=100, price="250")

    engine_a = make_engine(repo)
    engine_a.snapshot(inputs, _t())

    engine_b = make_engine(repo)
    recomputed = engine_b.compute(inputs, now=_t())
    latest = engine_b.get_latest(account_id=acc, trading_mode="PAPER")

    assert latest.market_value == recomputed.market_value == Decimal("25000.0000")
