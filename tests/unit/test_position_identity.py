"""Phase 11 — position identity tests."""

from __future__ import annotations

from uuid import uuid4

import pytest

from alpha_algo_position_engine.engine import PositionEngine
from alpha_algo_position_engine.errors import PositionIdentityError
from alpha_algo_position_engine.identity import (
    build_position_identity,
    compute_position_key,
)

from position_test_support import InMemoryPositionRepository, make_fill


def make_engine(repo=None):
    return PositionEngine(
        repository=repo or InMemoryPositionRepository(),
        global_halt_active=lambda: False,
    )


def test_position_key_is_deterministic():
    sid, iid = uuid4(), uuid4()
    k1 = compute_position_key(strategy_run_id=sid, instrument_id=iid, trading_mode="paper")
    k2 = compute_position_key(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER")
    assert k1 == k2  # mode is case-normalized


def test_position_key_distinguishes_dimensions():
    a, b, c, _ = uuid4(), uuid4(), uuid4(), uuid4()
    base = compute_position_key(strategy_run_id=a, instrument_id=b, trading_mode="PAPER")
    assert base != compute_position_key(strategy_run_id=c, instrument_id=b, trading_mode="PAPER")
    assert base != compute_position_key(strategy_run_id=a, instrument_id=c, trading_mode="PAPER")
    assert base != compute_position_key(strategy_run_id=a, instrument_id=b, trading_mode="BACKTEST")


def test_same_identity_accumulates_into_one_position():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))
    engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="50", price="110"))

    snap = engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER")
    assert snap.quantity == 150
    assert len(repo.positions) == 1


def test_different_strategy_runs_are_distinct_positions():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    iid = uuid4()

    engine.apply_fill(make_fill(strategy_run_id=uuid4(), instrument_id=iid, side="BUY", quantity="100"))
    engine.apply_fill(make_fill(strategy_run_id=uuid4(), instrument_id=iid, side="BUY", quantity="100"))

    assert len(repo.positions) == 2


def test_account_mismatch_is_rejected():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid = uuid4(), uuid4()

    engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=uuid4(), side="BUY", quantity="100"))
    with pytest.raises(PositionIdentityError):
        engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=uuid4(), side="BUY", quantity="10"))


def test_build_position_identity_normalizes_mode():
    ident = build_position_identity(strategy_run_id=uuid4(), instrument_id=uuid4(), trading_mode="paper")
    assert ident.trading_mode == "PAPER"
