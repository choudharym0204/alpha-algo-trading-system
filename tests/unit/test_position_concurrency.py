"""Phase 11 — concurrency + restart-recovery tests."""

from __future__ import annotations

import threading
from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_position_engine.contracts import PositionApplyStatus
from alpha_algo_position_engine.engine import PositionEngine
from alpha_algo_position_engine.errors import PositionPersistenceError

from position_test_support import InMemoryPositionRepository, make_fill


def make_engine(repo=None):
    return PositionEngine(
        repository=repo or InMemoryPositionRepository(),
        global_halt_active=lambda: False,
    )


def _run_threads(fns):
    threads = [threading.Thread(target=fn) for fn in fns]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


def test_two_fills_same_position_concurrently_no_lost_update():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    results = {}

    def buy100():
        r = engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))
        results["a"] = r

    def buy50():
        r = engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="50", price="110"))
        results["b"] = r

    _run_threads([buy100, buy50])

    snap = engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER")
    assert snap.quantity == 150
    assert snap.average_price == Decimal("103.3333")


def test_many_fills_concurrently_no_double_count():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    def buy(i):
        engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="10", price="100"))

    _run_threads([(lambda i=i: buy(i)) for i in range(20)])

    snap = engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER")
    assert snap.quantity == 200
    assert len(repo.applied) == 20


def test_same_execution_concurrently_applies_once():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    fill = make_fill(side="BUY", quantity="100", price="100")

    outcomes = []

    def apply():
        outcomes.append(engine.apply_fill(fill))

    _run_threads([apply, apply])

    statuses = sorted(o.status for o in outcomes)
    assert statuses == [PositionApplyStatus.APPLIED, PositionApplyStatus.DUPLICATE]
    snap = engine.get_position(strategy_run_id=fill.strategy_run_id, instrument_id=fill.instrument_id, trading_mode="PAPER")
    assert snap.quantity == 100  # not 200
    assert len(repo.applied) == 1


def test_different_positions_concurrently_do_not_interfere():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, acc = uuid4(), uuid4()

    def buy(instrument_id):
        engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=instrument_id, account_id=acc, side="BUY", quantity="100", price="100"))

    iids = [uuid4() for _ in range(10)]
    _run_threads([(lambda i=i: buy(i)) for i in iids])

    assert len(repo.positions) == 10
    for iid in iids:
        snap = engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER")
        assert snap.quantity == 100


def test_restart_after_commit_recovers_state():
    repo = InMemoryPositionRepository()
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    engine1 = make_engine(repo)
    engine1.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))

    # "restart": a fresh engine over the same durable repository.
    engine2 = make_engine(repo)
    snap = engine2.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER")
    assert snap.quantity == 100
    assert snap.average_price == Decimal("100.0000")


def test_restart_before_commit_rolls_back_cleanly():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    repo.fail_next_apply = True
    with pytest.raises(PositionPersistenceError):
        engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))

    # No partial mutation.
    snap = engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER")
    assert snap.quantity == 0
    assert len(repo.applied) == 0

    # Retry succeeds after the transient failure clears.
    engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))
    assert engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER").quantity == 100


def test_replay_after_restart_is_idempotent():
    repo = InMemoryPositionRepository()
    fill = make_fill(side="BUY", quantity="100", price="100")

    engine1 = make_engine(repo)
    engine1.apply_fill(fill)

    engine2 = make_engine(repo)
    dup = engine2.apply_fill(fill)
    assert dup.status == PositionApplyStatus.DUPLICATE
    assert len(repo.applied) == 1
