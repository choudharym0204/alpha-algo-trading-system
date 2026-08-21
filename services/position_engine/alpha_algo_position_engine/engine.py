"""Position Engine (Phase 11).

Consumes normalized execution/fill events (``PositionFill``) and maintains a
durable, authoritative, idempotent position state keyed by
**(strategy_run_id, instrument_id, trading_mode)** — the canonical identity
preserved from the existing ``positions`` schema.

Responsibilities: position creation/update, fill application, quantity
aggregation, weighted average price, open/closed state, partial-fill handling,
duplicate-fill protection, conflict detection, over-close protection, append-only
position events, snapshots, and restart recovery. The engine is **broker-
independent**, **LONG-only** (no short / no flip), and **never enables LIVE**.

The engine does NOT call brokers, submit orders, evaluate risk, aggregate a
portfolio, or compute P&L (Phases 12-14 own those).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import Callable, Protocol
from uuid import UUID

from alpha_algo_position_engine.arithmetic import apply_buy, apply_sell
from alpha_algo_position_engine.contracts import (
    PositionApplyStatus,
    PositionEventType,
    PositionFill,
    PositionIdentity,
    PositionResult,
    PositionSide,
    PositionSnapshot,
    PositionState,
    PositionStatus,
)
from alpha_algo_position_engine.errors import (
    DuplicateApplyError,
    PositionConflictError,
    PositionIdentityError,
    PositionModeError,
    PositionOverCloseError,
    PositionPersistenceError,
    PositionValidationError,
)
from alpha_algo_position_engine.identity import (
    build_position_identity,
    fill_content_hash,
)
from alpha_algo_position_engine.metrics import PositionMetrics

_ALLOWED_MODES = frozenset({"BACKTEST", "PAPER"})


@dataclass(frozen=True)
class PositionEventData:
    """Append-only event payload the engine computes for the repository."""

    event_type: PositionEventType
    quantity_before: int
    quantity_after: int
    execution_id: str
    content_hash: str
    occurred_at: datetime
    reason: str = ""


@dataclass(frozen=True)
class PositionApplyPlan:
    """Deterministic new state + event produced by applying one fill."""

    new_state: PositionState
    event: PositionEventData


class PositionRepository(Protocol):
    """Durable position state the engine relies on (positions + events)."""

    def find_fill_hash(self, execution_id: str) -> str | None: ...

    def load_position(self, identity: PositionIdentity) -> PositionState | None: ...

    def load_position_by_id(self, position_id: UUID) -> PositionState | None: ...

    def list_positions(
        self, *, strategy_run_id: UUID | None = None, trading_mode: str | None = None
    ) -> list[PositionState]: ...

    def persist_apply(
        self,
        *,
        identity: PositionIdentity,
        state: PositionState,
        event: PositionEventData,
        fill: PositionFill,
    ) -> None: ...

    def record_conflict(self, fill: PositionFill, original_hash: str) -> None: ...


class PositionEngine:
    def __init__(
        self,
        *,
        repository: PositionRepository | None = None,
        metrics: PositionMetrics | None = None,
        clock: Callable[[], datetime] | None = None,
        global_halt_active: Callable[[], bool] | None = None,
    ) -> None:
        self._repository = repository
        self._metrics = metrics or PositionMetrics()
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        # Fail-closed default: global halt is active unless a provider says otherwise.
        self._global_halt_active = global_halt_active or (lambda: True)
        self._locks: dict[tuple, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # ------------------------------------------------------------------ apply
    def apply_fill(self, fill: PositionFill) -> PositionResult:
        started = perf_counter()
        self._validate(fill)

        identity = build_position_identity(
            strategy_run_id=fill.strategy_run_id,
            instrument_id=fill.instrument_id,
            trading_mode=fill.trading_mode,
        )

        if self._repository is None:
            raise PositionPersistenceError("no position repository configured")

        # Fast-path idempotency + conflict detection (durable backstop below).
        existing_hash = self._repository.find_fill_hash(fill.execution_id)
        if existing_hash is not None:
            return self._resolve_replay(fill, identity, existing_hash)

        with self._lock(identity):
            current = self._repository.load_position(identity)
            plan = self._compute_plan(current, fill)
            try:
                self._repository.persist_apply(
                    identity=identity,
                    state=plan.new_state,
                    event=plan.event,
                    fill=fill,
                )
            except DuplicateApplyError:
                # Concurrent duplicate won the unique-constraint race.
                stored_hash = self._repository.find_fill_hash(fill.execution_id)
                return self._resolve_replay(fill, identity, stored_hash)

        self._record_event(plan.event.event_type)
        self._metrics.record_latency(perf_counter() - started)
        return PositionResult(
            status=PositionApplyStatus.APPLIED,
            event_type=plan.event.event_type,
            snapshot=self._to_snapshot(plan.new_state),
            quantity_before=plan.event.quantity_before,
            quantity_after=plan.event.quantity_after,
        )

    def _resolve_replay(
        self, fill: PositionFill, identity: PositionIdentity, stored_hash: str | None
    ) -> PositionResult:
        current_hash = fill_content_hash(fill)
        if stored_hash == current_hash:
            self._metrics.record_duplicate()
            current = self._repository.load_position(identity)
            if current is None:
                snapshot = self._flat_snapshot(
                    fill.strategy_run_id, fill.instrument_id, fill.trading_mode
                )
                qty = 0
            else:
                snapshot = self._to_snapshot(current)
                qty = current.quantity
            return PositionResult(
                status=PositionApplyStatus.DUPLICATE,
                event_type=None,
                snapshot=snapshot,
                quantity_before=qty,
                quantity_after=qty,
                duplicate=True,
            )
        # Same execution identity, different payload -> CONFLICT (preserve original).
        self._repository.record_conflict(fill, stored_hash or "")
        self._metrics.record_conflict()
        raise PositionConflictError(fill.execution_id)

    def _validate(self, fill: PositionFill) -> None:
        mode = (fill.trading_mode or "").upper()
        if mode == "LIVE":
            self._metrics.record_rejection()
            raise PositionModeError("LIVE trading is disabled (fail-closed)")
        if mode not in _ALLOWED_MODES:
            self._metrics.record_rejection()
            raise PositionModeError(f"unknown trading mode: {fill.trading_mode}")
        if self._global_halt_active():
            self._metrics.record_rejection()
            raise PositionValidationError(
                "global trading halt is active; position updates refused"
            )
        if fill.side not in {"BUY", "SELL"}:
            self._metrics.record_rejection()
            raise PositionValidationError(f"unsupported side: {fill.side}")
        if fill.quantity <= Decimal("0"):
            self._metrics.record_rejection()
            raise PositionValidationError("fill quantity must be positive")
        if fill.quantity != fill.quantity.to_integral_value():
            self._metrics.record_rejection()
            raise PositionValidationError("fill quantity must be a whole number")
        if fill.price <= Decimal("0"):
            self._metrics.record_rejection()
            raise PositionValidationError("fill price must be positive")

    def _compute_plan(
        self, current: PositionState | None, fill: PositionFill
    ) -> PositionApplyPlan:
        quantity_before = self._quantity_or_zero(current)
        fill_qty = int(fill.quantity)

        if current is None:
            if fill.side == "SELL":
                # SELL with no open long -> would open short (unsupported).
                self._metrics.record_rejection()
                raise PositionOverCloseError(0, fill_qty)
            delta = apply_buy(
                quantity=0,
                average_price=None,
                opened_at=None,
                closed_at=None,
                fill_quantity=fill_qty,
                fill_price=fill.price,
                occurred_at=fill.occurred_at,
            )
            new_state = PositionState(
                position_id=None,
                strategy_run_id=fill.strategy_run_id,
                instrument_id=fill.instrument_id,
                trading_mode=fill.trading_mode.upper(),
                account_id=fill.account_id,
                quantity=delta.quantity,
                average_price=delta.average_price,
                status=delta.status,
                opened_at=delta.opened_at,
                closed_at=delta.closed_at,
                last_execution_id=fill.execution_id,
            )
        else:
            if current.account_id is not None and current.account_id != fill.account_id:
                self._metrics.record_rejection()
                raise PositionIdentityError(
                    "fill account does not match existing position account"
                )
            if fill.side == "BUY":
                delta = apply_buy(
                    quantity=current.quantity,
                    average_price=current.average_price,
                    opened_at=current.opened_at,
                    closed_at=current.closed_at,
                    fill_quantity=fill_qty,
                    fill_price=fill.price,
                    occurred_at=fill.occurred_at,
                )
            else:
                try:
                    delta = apply_sell(
                        quantity=current.quantity,
                        average_price=current.average_price,
                        opened_at=current.opened_at,
                        closed_at=current.closed_at,
                        fill_quantity=fill_qty,
                        fill_price=fill.price,
                        occurred_at=fill.occurred_at,
                    )
                except ValueError as exc:
                    if "exceeds" in str(exc):
                        self._metrics.record_rejection()
                        raise PositionOverCloseError(current.quantity, fill_qty) from exc
                    raise
            new_state = PositionState(
                position_id=current.position_id,
                strategy_run_id=current.strategy_run_id,
                instrument_id=current.instrument_id,
                trading_mode=current.trading_mode,
                account_id=current.account_id or fill.account_id,
                quantity=delta.quantity,
                average_price=delta.average_price,
                status=delta.status,
                opened_at=delta.opened_at,
                closed_at=delta.closed_at,
                last_execution_id=fill.execution_id,
            )

        return PositionApplyPlan(
            new_state=new_state,
            event=PositionEventData(
                event_type=PositionEventType(delta.event_type),
                quantity_before=quantity_before,
                quantity_after=delta.quantity,
                execution_id=fill.execution_id,
                content_hash=fill_content_hash(fill),
                occurred_at=fill.occurred_at,
                reason=f"fill {fill.side} {fill_qty} @ {fill.price}",
            ),
        )

    def _record_event(self, event_type: PositionEventType) -> None:
        if event_type == PositionEventType.POSITION_OPENED:
            self._metrics.record_opened()
        elif event_type == PositionEventType.POSITION_INCREASED:
            self._metrics.record_increased()
        elif event_type == PositionEventType.POSITION_DECREASED:
            self._metrics.record_decreased()
        elif event_type == PositionEventType.POSITION_CLOSED:
            self._metrics.record_closed()

    def _lock(self, identity: PositionIdentity) -> threading.Lock:
        key = identity.as_tuple()
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
        return lock

    # ------------------------------------------------------------------ reads
    def get_position(
        self, *, strategy_run_id: UUID, instrument_id: UUID, trading_mode: str
    ) -> PositionSnapshot:
        if self._repository is None:
            return self._flat_snapshot(strategy_run_id, instrument_id, trading_mode)
        identity = build_position_identity(
            strategy_run_id=strategy_run_id,
            instrument_id=instrument_id,
            trading_mode=trading_mode,
        )
        state = self._repository.load_position(identity)
        if state is None:
            return self._flat_snapshot(strategy_run_id, instrument_id, trading_mode)
        return self._to_snapshot(state)

    def list_positions(
        self, *, strategy_run_id: UUID | None = None, trading_mode: str | None = None
    ) -> list[PositionSnapshot]:
        if self._repository is None:
            return []
        return [
            self._to_snapshot(state)
            for state in self._repository.list_positions(
                strategy_run_id=strategy_run_id, trading_mode=trading_mode
            )
        ]

    # ------------------------------------------------------------ snapshots
    @staticmethod
    def _quantity_or_zero(state: PositionState | None) -> int:
        return 0 if state is None else state.quantity

    def _to_snapshot(self, state: PositionState) -> PositionSnapshot:
        side = PositionSide.LONG if state.quantity > 0 else None
        return PositionSnapshot(
            position_id=state.position_id,
            account_id=state.account_id,
            instrument_id=state.instrument_id,
            strategy_run_id=state.strategy_run_id,
            trading_mode=state.trading_mode,
            side=side,
            quantity=state.quantity,
            average_price=state.average_price,
            status=state.status,
            opened_at=state.opened_at,
            closed_at=state.closed_at,
            last_execution_id=state.last_execution_id,
        )

    def _flat_snapshot(
        self, strategy_run_id: UUID, instrument_id: UUID, trading_mode: str
    ) -> PositionSnapshot:
        return PositionSnapshot(
            position_id=None,
            account_id=None,
            instrument_id=instrument_id,
            strategy_run_id=strategy_run_id,
            trading_mode=trading_mode.upper(),
            side=None,
            quantity=0,
            average_price=None,
            status=PositionStatus.FLAT,
            opened_at=None,
            closed_at=None,
            last_execution_id=None,
        )
