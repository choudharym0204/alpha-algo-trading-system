"""Phase 11 — end-to-end: BrokerOrderEvent → normalized fill → position state."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from alpha_algo_execution_engine.events import BrokerOrderEvent, OrderEventType
from alpha_algo_execution_engine.identity import compute_event_identity
from alpha_algo_position_engine.engine import PositionEngine
from alpha_algo_position_engine.identity import normalize_fill

from position_test_support import InMemoryPositionRepository


def make_engine(repo=None):
    return PositionEngine(repository=repo or InMemoryPositionRepository(), global_halt_active=lambda: False)


def _fill_event(order_id, fill_quantity, side, *, source_event_id=None):
    return BrokerOrderEvent(
        order_id=order_id,
        event_type=OrderEventType.FILL,
        occurred_at=datetime.now(UTC),
        reason="broker fill",
        broker_order_id="broker-1",
        fill_quantity=Decimal(fill_quantity),
        metadata={"source_event_id": source_event_id} if source_event_id else {},
    )


def test_fill_event_to_position_roundtrip():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)

    order_id = uuid4()
    sid, iid, acc = uuid4(), uuid4(), uuid4()
    event = _fill_event(order_id, "100", "BUY", source_event_id="src-1")
    execution_id = compute_event_identity(event)

    fill = normalize_fill(
        execution_id=execution_id,
        order_id=order_id,
        account_id=acc,
        instrument_id=iid,
        strategy_run_id=sid,
        trading_mode="PAPER",
        side="BUY",
        quantity=event.fill_quantity,
        price=Decimal("100"),
        occurred_at=event.occurred_at,
        broker_order_id=event.broker_order_id,
    )

    result = engine.apply_fill(fill)
    assert result.snapshot.quantity == 100
    assert result.snapshot.average_price == Decimal("100.0000")

    read = engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER")
    assert read.quantity == 100
    assert read.last_execution_id == execution_id


def test_duplicate_broker_event_replay_is_idempotent():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)

    order_id = uuid4()
    sid, iid, acc = uuid4(), uuid4(), uuid4()
    event = _fill_event(order_id, "100", "BUY", source_event_id="src-1")
    execution_id = compute_event_identity(event)

    def build():
        return normalize_fill(
            execution_id=execution_id, order_id=order_id, account_id=acc,
            instrument_id=iid, strategy_run_id=sid, trading_mode="PAPER",
            side="BUY", quantity=event.fill_quantity, price=Decimal("100"),
            occurred_at=event.occurred_at, broker_order_id=event.broker_order_id,
        )

    engine.apply_fill(build())
    dup = engine.apply_fill(build())

    assert dup.duplicate is True
    assert len(repo.applied) == 1
    assert engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER").quantity == 100


def test_buy_then_sell_close_via_events():
    repo = InMemoryPositionRepository()
    engine = make_engine(repo)

    order_buy, order_sell = uuid4(), uuid4()
    sid, iid, acc = uuid4(), uuid4(), uuid4()

    buy_ev = _fill_event(order_buy, "100", "BUY", source_event_id="src-buy")
    engine.apply_fill(normalize_fill(
        execution_id=compute_event_identity(buy_ev), order_id=order_buy,
        account_id=acc, instrument_id=iid, strategy_run_id=sid,
        trading_mode="PAPER", side="BUY", quantity=buy_ev.fill_quantity,
        price=Decimal("100"), occurred_at=buy_ev.occurred_at,
    ))

    sell_ev = _fill_event(order_sell, "100", "SELL", source_event_id="src-sell")
    engine.apply_fill(normalize_fill(
        execution_id=compute_event_identity(sell_ev), order_id=order_sell,
        account_id=acc, instrument_id=iid, strategy_run_id=sid,
        trading_mode="PAPER", side="SELL", quantity=sell_ev.fill_quantity,
        price=Decimal("120"), occurred_at=sell_ev.occurred_at,
    ))

    read = engine.get_position(strategy_run_id=sid, instrument_id=iid, trading_mode="PAPER")
    assert read.quantity == 0
    assert read.average_price is None
    assert read.closed_at is not None
