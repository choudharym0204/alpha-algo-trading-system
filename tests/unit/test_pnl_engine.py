"""Phase 13 — P&L engine (record_fill, idempotency, mode/halt) tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from alpha_algo_pnl_engine.contracts import PnlApplyStatus, PnlEventType
from alpha_algo_pnl_engine.engine import PnlEngine
from alpha_algo_pnl_engine.errors import (
    PnlModeError,
    PnlOverCloseError,
    PnlValidationError,
)

from pnl_test_support import (
    InMemoryPnlRepository,
    make_cost,
    make_fill,
    make_position,
)


def make_engine(repo=None, halt=False):
    return PnlEngine(repository=repo or InMemoryPnlRepository(), global_halt_active=lambda: halt)


def _t():
    return datetime(2026, 8, 20, 10, 0, tzinfo=UTC)


def test_buy_fill_produces_no_realized_event():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    fill = make_fill(side="BUY", quantity="100", price="100")
    result = engine.record_fill(fill=fill, position_before=make_position(quantity=0, average_price=None))
    assert result.status == PnlApplyStatus.APPLIED
    assert result.realized is None
    assert result.event is None
    assert len(repo.events) == 0


def test_partial_close_realizes_profit():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    acc, strat, inst = uuid4(), uuid4(), uuid4()
    position = make_position(position_id=uuid4(), account_id=acc, strategy_run_id=strat, instrument_id=inst, quantity=100, average_price="100")
    fill = make_fill(account_id=acc, strategy_run_id=strat, instrument_id=inst, side="SELL", quantity="40", price="120")

    result = engine.record_fill(fill=fill, position_before=position)

    assert result.status == PnlApplyStatus.APPLIED
    assert result.realized.gross_pnl == Decimal("800.0000")  # (120-100)*40
    assert result.realized.closed_quantity == 40
    assert result.event.event_type == PnlEventType.REALIZED_PNL
    assert len(repo.events) == 1


def test_full_close_realizes_profit():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    position = make_position(quantity=100, average_price="100")
    fill = make_fill(side="SELL", quantity="100", price="110")
    result = engine.record_fill(fill=fill, position_before=position)
    assert result.realized.gross_pnl == Decimal("1000.0000")
    assert result.realized.closed_quantity == 100


def test_losing_close_realizes_negative():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    position = make_position(quantity=100, average_price="100")
    fill = make_fill(side="SELL", quantity="100", price="90")
    result = engine.record_fill(fill=fill, position_before=position)
    assert result.realized.gross_pnl == Decimal("-1000.0000")


def test_accumulation_then_close_uses_weighted_average():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    position = make_position(quantity=150, average_price="103.3333")
    fill = make_fill(side="SELL", quantity="40", price="120")
    result = engine.record_fill(fill=fill, position_before=position)
    assert result.realized.gross_pnl == Decimal("666.6680")


def test_costs_subtracted_from_net():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    position = make_position(quantity=100, average_price="100")
    fill = make_fill(side="SELL", quantity="100", price="110")
    result = engine.record_fill(fill=fill, position_before=position, costs=(make_cost("50"), make_cost("25", kind="exchange")))
    assert result.realized.gross_pnl == Decimal("1000.0000")
    assert result.realized.costs == Decimal("75.0000")
    assert result.realized.net_pnl == Decimal("925.0000")


def test_over_close_rejected():
    engine = make_engine()
    position = make_position(quantity=50, average_price="100")
    fill = make_fill(side="SELL", quantity="60", price="110")
    with pytest.raises(PnlOverCloseError):
        engine.record_fill(fill=fill, position_before=position)


def test_sell_on_flat_rejected():
    engine = make_engine()
    position = make_position(quantity=0, average_price=None)
    fill = make_fill(side="SELL", quantity="10", price="110")
    with pytest.raises(PnlOverCloseError):
        engine.record_fill(fill=fill, position_before=position)


def test_live_mode_rejected():
    engine = make_engine()
    fill = make_fill(trading_mode="LIVE", side="BUY")
    with pytest.raises(PnlModeError):
        engine.record_fill(fill=fill, position_before=make_position(quantity=0))


def test_halt_blocks_record_fill():
    engine = make_engine(halt=True)
    fill = make_fill(side="BUY")
    with pytest.raises(PnlValidationError):
        engine.record_fill(fill=fill, position_before=make_position(quantity=0))


def test_duplicate_execution_is_idempotent():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    position = make_position(quantity=100, average_price="100")
    fill = make_fill(side="SELL", quantity="40", price="120", execution_id="exec-1")

    r1 = engine.record_fill(fill=fill, position_before=position)
    r2 = engine.record_fill(fill=fill, position_before=position)

    assert r1.status == PnlApplyStatus.APPLIED
    assert r2.status == PnlApplyStatus.DUPLICATE
    assert len(repo.events) == 1  # no second accounting effect


def test_same_execution_different_payload_is_conflict():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    position = make_position(quantity=100, average_price="100")
    fill_a = make_fill(side="SELL", quantity="40", price="120", execution_id="exec-2")
    fill_b = make_fill(side="SELL", quantity="40", price="130", execution_id="exec-2")

    r1 = engine.record_fill(fill=fill_a, position_before=position)
    r2 = engine.record_fill(fill=fill_b, position_before=position)

    assert r1.status == PnlApplyStatus.APPLIED
    assert r2.status == PnlApplyStatus.CONFLICT
    assert r2.conflict_original is not None
    # Original fact preserved (not overwritten).
    assert repo.events["exec-2"].price == Decimal("120.0000")


def test_reopen_starts_new_cost_basis_cycle():
    repo = InMemoryPnlRepository()
    engine = make_engine(repo)
    acc, strat, inst = uuid4(), uuid4(), uuid4()

    # Cycle 1: buy 100 @ 100, close @ 110 -> realized 1000.
    pos1 = make_position(position_id=uuid4(), account_id=acc, strategy_run_id=strat, instrument_id=inst, quantity=100, average_price="100")
    close1 = make_fill(account_id=acc, strategy_run_id=strat, instrument_id=inst, side="SELL", quantity="100", price="110", execution_id="e1")
    r1 = engine.record_fill(fill=close1, position_before=pos1)
    assert r1.realized.gross_pnl == Decimal("1000.0000")

    # Reopen: new buy cycle at 105 (Phase 11 computes new average), then close @ 115.
    pos2 = make_position(position_id=uuid4(), account_id=acc, strategy_run_id=strat, instrument_id=inst, quantity=50, average_price="105")
    close2 = make_fill(account_id=acc, strategy_run_id=strat, instrument_id=inst, side="SELL", quantity="50", price="115", execution_id="e2")
    r2 = engine.record_fill(fill=close2, position_before=pos2)
    # Realized uses the NEW cost basis (105), not the old 100.
    assert r2.realized.gross_pnl == Decimal("500.0000")
