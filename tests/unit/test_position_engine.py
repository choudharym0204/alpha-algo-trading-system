"""Phase 11 — Position Engine core tests (open/close/dup/conflict/invalid)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_position_engine.contracts import (
    PositionApplyStatus,
    PositionEventType,
    PositionSide,
    PositionStatus,
)
from alpha_algo_position_engine.engine import PositionEngine
from alpha_algo_position_engine.errors import (
    PositionConflictError,
    PositionOverCloseError,
    PositionValidationError,
)

from position_test_support import InMemoryPositionRepository, make_fill


def make_engine(repo=None):
    return PositionEngine(
        repository=repo or InMemoryPositionRepository(),
        global_halt_active=lambda: False,
    )


def test_first_buy_opens_position():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    result = engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))

    assert result.status == PositionApplyStatus.APPLIED
    assert result.event_type == PositionEventType.POSITION_OPENED
    assert result.quantity_before == 0
    assert result.quantity_after == 100
    assert result.snapshot.quantity == 100
    assert result.snapshot.side == PositionSide.LONG
    assert result.snapshot.average_price == Decimal("100.0000")
    assert result.snapshot.status == PositionStatus.OPEN


def test_repeated_buy_accumulates_with_weighted_average():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))
    result = engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="50", price="110"))

    assert result.event_type == PositionEventType.POSITION_INCREASED
    assert result.snapshot.quantity == 150
    assert result.snapshot.average_price == Decimal("103.3333")


def test_partial_close_then_full_close():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))
    p1 = engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="SELL", quantity="30", price="120"))
    assert p1.event_type == PositionEventType.POSITION_DECREASED
    assert p1.snapshot.quantity == 70

    p2 = engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="SELL", quantity="20", price="120"))
    assert p2.snapshot.quantity == 50

    p3 = engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="SELL", quantity="50", price="120"))
    assert p3.event_type == PositionEventType.POSITION_CLOSED
    assert p3.snapshot.quantity == 0
    assert p3.snapshot.status == PositionStatus.CLOSED
    assert p3.snapshot.average_price is None
    assert p3.snapshot.closed_at is not None


def test_reopen_after_close():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))
    engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="SELL", quantity="100", price="120"))
    reopen = engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="40", price="90"))

    assert reopen.event_type == PositionEventType.POSITION_OPENED
    assert reopen.snapshot.quantity == 40
    assert reopen.snapshot.average_price == Decimal("90.0000")
    assert reopen.snapshot.status == PositionStatus.OPEN
    assert reopen.snapshot.closed_at is None
    assert len(repo.positions) == 1  # reused the same canonical row


def test_duplicate_fill_is_idempotent():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    fill = make_fill(side="BUY", quantity="100", price="100")

    engine.apply_fill(fill)
    dup = engine.apply_fill(fill)

    assert dup.status == PositionApplyStatus.DUPLICATE
    assert dup.duplicate is True
    assert dup.snapshot.quantity == 100
    assert repo.positions[next(iter(repo.positions))].quantity == 100  # no double count
    assert len(repo.applied) == 1


def test_conflicting_fill_is_detected_and_preserves_original():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    exec_id = "exec-same"
    engine.apply_fill(make_fill(execution_id=exec_id, strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))

    with pytest.raises(PositionConflictError):
        engine.apply_fill(make_fill(execution_id=exec_id, strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="80", price="101"))

    # Original preserved + conflict evidence recorded.
    snap = engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER")
    assert snap.quantity == 100
    assert snap.average_price == Decimal("100.0000")
    assert len(repo.conflicts) == 1


def test_severe_over_close_rejected():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))
    with pytest.raises(PositionOverCloseError):
        engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="SELL", quantity="150", price="120"))
    # Position unchanged.
    assert engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER").quantity == 100


def test_sell_on_flat_position_rejected():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    with pytest.raises(PositionOverCloseError):
        engine.apply_fill(make_fill(strategy_run_id=sid, instrument_id=iid, account_id=acc, side="SELL", quantity="10", price="100"))


def test_invalid_fill_values_rejected():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)

    # Construction-time structural validation (fail fast).
    with pytest.raises(ValueError):
        make_fill(side="BUY", quantity="0", price="100")
    with pytest.raises(ValueError):
        make_fill(side="BUY", quantity="-5", price="100")
    with pytest.raises(ValueError):
        make_fill(side="BUY", quantity="100", price="0")
    with pytest.raises(ValueError):
        make_fill(side="HOLD", quantity="100", price="100")
    # Engine-level validation (typed, non-leaky error).
    with pytest.raises(PositionValidationError):
        engine.apply_fill(make_fill(side="BUY", quantity="10.5", price="100"))


def test_last_execution_id_is_recorded():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    engine.apply_fill(make_fill(execution_id="e1", strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="100", price="100"))
    engine.apply_fill(make_fill(execution_id="e2", strategy_run_id=sid, instrument_id=iid, account_id=acc, side="BUY", quantity="10", price="101"))

    snap = engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER")
    assert snap.last_execution_id == "e2"
