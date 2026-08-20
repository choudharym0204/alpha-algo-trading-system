"""Phase 12 — snapshot lifecycle / persistence / recovery tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_portfolio_engine.engine import PortfolioEngine
from alpha_algo_portfolio_engine.errors import PortfolioPersistenceError
from alpha_algo_portfolio_engine.identity import snapshot_content_hash

from portfolio_test_support import (
    InMemoryPortfolioRepository,
    make_funds,
    make_inputs,
    make_position,
    make_price,
)


def make_engine(repo):
    return PortfolioEngine(repository=repo, global_halt_active=lambda: False)


def _t(ts: str = "2026-08-20T10:00:00+00:00"):
    return datetime.fromisoformat(ts)


def _priced_inputs(*, quantity=100, price="100", cash="1000000"):
    iid = uuid4()
    pos = make_position(instrument_id=iid, quantity=quantity)
    return make_inputs(
        positions=(pos,),
        funds=make_funds(available_cash=cash),
        prices={iid: make_price(iid, price=price)},
    ), iid


def test_snapshot_creates_and_persists():
    repo = InMemoryPortfolioRepository()
    engine = make_engine(repo)
    inputs, _ = _priced_inputs()
    result = engine.snapshot(inputs, _t())

    assert result.duplicate is False
    assert result.snapshot.snapshot_id is not None
    assert result.snapshot.market_value == Decimal("10000.0000")
    assert result.snapshot.status.value == "READY"

    latest = engine.get_latest(account_id=inputs.account_id, trading_mode="PAPER")
    assert latest is not None
    assert latest.snapshot_at == _t()
    assert latest.market_value == Decimal("10000.0000")


def test_duplicate_snapshot_is_idempotent():
    repo = InMemoryPortfolioRepository()
    engine = make_engine(repo)
    inputs, _ = _priced_inputs()

    r1 = engine.snapshot(inputs, _t())
    r2 = engine.snapshot(inputs, _t())

    assert r1.duplicate is False
    assert r2.duplicate is True
    assert r1.snapshot.snapshot_id == r2.snapshot.snapshot_id
    assert len(repo.snapshots) == 1


def test_same_state_recalculation_is_deterministic():
    repo = InMemoryPortfolioRepository()
    engine = make_engine(repo)
    inputs, _ = _priced_inputs(quantity=100, price="123.45")

    c1 = engine.compute(inputs, now=_t())
    c2 = engine.compute(inputs, now=_t())

    for field in ("gross_exposure", "net_exposure", "long_exposure", "short_exposure", "market_value", "equity_value"):
        assert getattr(c1, field) == getattr(c2, field), field
    assert c1.position_count == c2.position_count


def test_different_state_recalculation_differs():
    repo = InMemoryPortfolioRepository()
    engine = make_engine(repo)
    acc = uuid4()
    iid = uuid4()
    p = make_position(instrument_id=iid, quantity=100)
    base = dict(positions=(p,), funds=make_funds())

    c1 = engine.compute(make_inputs(account_id=acc, prices={iid: make_price(iid, "100")}, **base), now=_t())
    c2 = engine.compute(make_inputs(account_id=acc, prices={iid: make_price(iid, "110")}, **base), now=_t())

    assert c1.market_value == Decimal("10000.0000")
    assert c2.market_value == Decimal("11000.0000")


def test_persistence_failure_rolls_back():
    repo = InMemoryPortfolioRepository()
    engine = make_engine(repo)
    inputs, _ = _priced_inputs()
    repo.fail_next_save = True

    with pytest.raises(PortfolioPersistenceError):
        engine.snapshot(inputs, _t())

    assert len(repo.snapshots) == 0
    assert engine.get_latest(account_id=inputs.account_id, trading_mode="PAPER") is None


def test_restart_recovery_recomputes_same_state():
    repo = InMemoryPortfolioRepository()
    inputs, _ = _priced_inputs(quantity=100, price="250")

    # "Before restart": persist one snapshot.
    engine_a = make_engine(repo)
    engine_a.snapshot(inputs, _t())

    # "After restart": fresh engine over the same durable repository.
    engine_b = make_engine(repo)
    recomputed = engine_b.compute(inputs, now=_t())

    latest = engine_b.get_latest(account_id=inputs.account_id, trading_mode="PAPER")
    assert latest.market_value == recomputed.market_value == Decimal("25000.0000")


def test_snapshot_content_hash_changes_with_state():
    acc = uuid4()
    h1 = snapshot_content_hash(
        account_id=acc, trading_mode="PAPER", snapshot_at=_t(),
        gross_exposure="10000", net_exposure="10000", long_exposure="10000",
        short_exposure="0", market_value="10000", cash_balance="1000000", position_count=1,
    )
    h2 = snapshot_content_hash(
        account_id=acc, trading_mode="PAPER", snapshot_at=_t(),
        gross_exposure="20000", net_exposure="20000", long_exposure="20000",
        short_exposure="0", market_value="20000", cash_balance="1000000", position_count=1,
    )
    assert h1 != h2
    assert len(h1) == 64  # sha256 hex
