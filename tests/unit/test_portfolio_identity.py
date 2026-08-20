"""Phase 12 — portfolio identity tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from alpha_algo_portfolio_engine.engine import PortfolioEngine
from alpha_algo_portfolio_engine.errors import PortfolioModeError
from alpha_algo_portfolio_engine.identity import (
    build_portfolio_identity,
    compute_portfolio_key,
)

from portfolio_test_support import (
    InMemoryPortfolioRepository,
    make_funds,
    make_inputs,
)


def make_engine(repo=None):
    return PortfolioEngine(
        repository=repo or InMemoryPortfolioRepository(),
        global_halt_active=lambda: False,
    )


def test_portfolio_key_is_deterministic_and_mode_normalized():
    acc = uuid4()
    assert compute_portfolio_key(account_id=acc, trading_mode="paper") == compute_portfolio_key(account_id=acc, trading_mode="PAPER")


def test_portfolio_key_distinguishes_account_and_mode():
    a, b = uuid4(), uuid4()
    base = compute_portfolio_key(account_id=a, trading_mode="PAPER")
    assert base != compute_portfolio_key(account_id=b, trading_mode="PAPER")
    assert base != compute_portfolio_key(account_id=a, trading_mode="BACKTEST")


def test_account_isolation():
    repo = InMemoryPortfolioRepository()
    engine = make_engine(repo)
    acc_a, acc_b = uuid4(), uuid4()
    t = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)

    engine.snapshot(make_inputs(account_id=acc_a, funds=make_funds()), t)
    engine.snapshot(make_inputs(account_id=acc_b, funds=make_funds()), t)

    assert len(repo.snapshots) == 2
    assert engine.get_latest(account_id=acc_a, trading_mode="PAPER").account_id == acc_a
    assert engine.get_latest(account_id=acc_b, trading_mode="PAPER").account_id == acc_b


def test_trading_mode_isolation():
    repo = InMemoryPortfolioRepository()
    engine = make_engine(repo)
    acc = uuid4()
    t = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)

    engine.snapshot(make_inputs(account_id=acc, trading_mode="PAPER", funds=make_funds()), t)
    engine.snapshot(make_inputs(account_id=acc, trading_mode="BACKTEST", funds=make_funds()), t)

    assert len(repo.snapshots) == 2
    assert engine.get_latest(account_id=acc, trading_mode="PAPER").trading_mode == "PAPER"
    assert engine.get_latest(account_id=acc, trading_mode="BACKTEST").trading_mode == "BACKTEST"


def test_duplicate_snapshot_same_identity_time_is_idempotent():
    repo = InMemoryPortfolioRepository()
    engine = make_engine(repo)
    acc = uuid4()
    t = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)

    r1 = engine.snapshot(make_inputs(account_id=acc, funds=make_funds()), t)
    r2 = engine.snapshot(make_inputs(account_id=acc, funds=make_funds()), t)

    assert r1.duplicate is False
    assert r2.duplicate is True
    assert len(repo.snapshots) == 1


def test_live_mode_rejected():
    engine = make_engine()
    with pytest.raises(PortfolioModeError):
        engine.snapshot(make_inputs(trading_mode="LIVE"), datetime(2026, 8, 20, 10, 0, tzinfo=UTC))


def test_build_identity_normalizes_mode():
    ident = build_portfolio_identity(account_id=uuid4(), trading_mode="paper")
    assert ident.trading_mode == "PAPER"
