"""Shared helpers for Phase 13 P&L-engine tests (not a test module)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from threading import Lock
from uuid import UUID, uuid4

from alpha_algo_pnl_engine.contracts import (
    CostComponent,
    PnlEvent,
    PnlEventType,
    PnlSnapshot,
)
from alpha_algo_pnl_engine.errors import DuplicateExecutionError, PnlPersistenceError
from alpha_algo_position_engine.contracts import PositionFill, PositionSnapshot


class _FakePosition:
    def __init__(
        self,
        *,
        position_id=None,
        account_id=None,
        instrument_id=None,
        strategy_run_id=None,
        trading_mode="PAPER",
        quantity=0,
        average_price=None,
        status="OPEN",
    ):
        self.position_id = position_id
        self.account_id = account_id
        self.instrument_id = instrument_id or uuid4()
        self.strategy_run_id = strategy_run_id or uuid4()
        self.trading_mode = trading_mode
        self.quantity = quantity
        self.average_price = average_price
        self.status = status


class _FakePrice:
    def __init__(self, instrument_id, price, observed_at=None):
        self.instrument_id = instrument_id
        self.price = Decimal(price)
        self.observed_at = observed_at or datetime.now(UTC)


def make_fill(
    *,
    execution_id=None,
    order_id=None,
    account_id=None,
    instrument_id=None,
    strategy_run_id=None,
    trading_mode="PAPER",
    side="BUY",
    quantity="100",
    price="100",
    occurred_at=None,
) -> PositionFill:
    return PositionFill(
        execution_id=execution_id or str(uuid4()),
        order_id=order_id or uuid4(),
        account_id=account_id or uuid4(),
        instrument_id=instrument_id or uuid4(),
        strategy_run_id=strategy_run_id or uuid4(),
        trading_mode=trading_mode,
        side=side,
        quantity=Decimal(quantity),
        price=Decimal(price),
        occurred_at=occurred_at or datetime.now(UTC),
    )


def make_position(
    *,
    position_id=None,
    account_id=None,
    instrument_id=None,
    strategy_run_id=None,
    trading_mode="PAPER",
    quantity=0,
    average_price=None,
    status="OPEN",
) -> _FakePosition:
    return _FakePosition(
        position_id=position_id,
        account_id=account_id,
        instrument_id=instrument_id,
        strategy_run_id=strategy_run_id,
        trading_mode=trading_mode,
        quantity=quantity,
        average_price=Decimal(average_price) if average_price is not None else None,
        status=status,
    )


def make_price(instrument_id, price, observed_at=None) -> _FakePrice:
    return _FakePrice(instrument_id, price, observed_at)


def make_cost(amount, kind="commission", source="broker") -> CostComponent:
    return CostComponent(amount=Decimal(amount), kind=kind, source=source)


class InMemoryPnlRepository:
    """In-memory P&L store mirroring durable semantics."""

    def __init__(self) -> None:
        self.events: dict[str, PnlEvent] = {}
        self.snapshots: dict[tuple, PnlSnapshot] = {}
        self.fail_next_save = False
        self._lock = Lock()

    def save_event(self, *, event: PnlEvent) -> PnlEvent:
        if self.fail_next_save:
            self.fail_next_save = False
            raise PnlPersistenceError("simulated DB failure")
        with self._lock:
            if event.execution_id in self.events:
                raise DuplicateExecutionError(f"duplicate {event.execution_id}")
            persisted = replace(event, id=uuid4())
            self.events[event.execution_id] = persisted
            return persisted

    def load_event(self, execution_id: str) -> PnlEvent | None:
        return self.events.get(execution_id)

    def list_events(
        self,
        *,
        account_id=None,
        strategy_run_id=None,
        instrument_id=None,
        position_id=None,
    ) -> list[PnlEvent]:
        out = []
        for e in self.events.values():
            if account_id is not None and e.account_id != account_id:
                continue
            if strategy_run_id is not None and e.strategy_run_id != strategy_run_id:
                continue
            if instrument_id is not None and e.instrument_id != instrument_id:
                continue
            if position_id is not None and e.position_id != position_id:
                continue
            out.append(e)
        out.sort(key=lambda e: e.occurred_at)
        return out

    def realized_pnl_for_position(self, *, position_id) -> Decimal:
        total = Decimal("0")
        for e in self.events.values():
            if e.position_id == position_id and e.event_type == PnlEventType.REALIZED_PNL:
                total += e.net_pnl
        return total

    def save_snapshot(self, *, snapshot: PnlSnapshot) -> PnlSnapshot:
        key = (snapshot.account_id, snapshot.trading_mode, snapshot.snapshot_at)
        with self._lock:
            if key in self.snapshots:
                raise DuplicateExecutionError("duplicate snapshot")
            persisted = replace(snapshot, snapshot_id=uuid4())
            self.snapshots[key] = persisted
            return persisted

    def load_snapshot(self, *, account_id, trading_mode, snapshot_at):
        return self.snapshots.get((account_id, trading_mode.upper(), snapshot_at))

    def load_latest_snapshot(self, *, account_id, trading_mode):
        matches = [
            s for (a, m, _t), s in self.snapshots.items()
            if a == account_id and m == trading_mode.upper()
        ]
        if not matches:
            return None
        return max(matches, key=lambda s: s.snapshot_at)
