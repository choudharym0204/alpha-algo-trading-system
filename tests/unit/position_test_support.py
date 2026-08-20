"""Shared helpers for Phase 11 position-engine tests (not a test module)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from alpha_algo_position_engine.contracts import (
    PositionFill,
    PositionIdentity,
    PositionState,
)
from alpha_algo_position_engine.engine import PositionEventData
from alpha_algo_position_engine.errors import (
    DuplicateApplyError,
    PositionPersistenceError,
)
from alpha_algo_position_engine.identity import fill_content_hash


def make_fill(
    *,
    execution_id: str | None = None,
    order_id: UUID | None = None,
    account_id: UUID | None = None,
    instrument_id: UUID | None = None,
    strategy_run_id: UUID | None = None,
    trading_mode: str = "PAPER",
    side: str = "BUY",
    quantity: str | Decimal = "100",
    price: str | Decimal = "100",
    occurred_at: datetime | None = None,
    **overrides,
) -> PositionFill:
    """Build a normalized fill with sensible defaults; override identity fields."""
    return PositionFill(
        execution_id=execution_id or f"exec-{uuid4()}",
        order_id=order_id or uuid4(),
        account_id=account_id or uuid4(),
        instrument_id=instrument_id or uuid4(),
        strategy_run_id=strategy_run_id or uuid4(),
        trading_mode=trading_mode,
        side=side,
        quantity=Decimal(quantity),
        price=Decimal(price),
        occurred_at=occurred_at or datetime.now(UTC),
        **overrides,
    )


class InMemoryPositionRepository:
    """In-memory position store mirroring the durable semantics.

    Simulates: the ``source_event_id`` unique constraint (duplicate apply raises
    ``DuplicateApplyError``), transactional failure/rollback (no partial
    mutation), and append-only conflict evidence.
    """

    def __init__(self) -> None:
        self.positions: dict[tuple, PositionState] = {}
        self.events: dict[str, str] = {}  # execution_id -> content_hash
        self.applied: list[PositionEventData] = []
        self.conflicts: list[dict] = []
        self.fail_next_apply = False

    def find_fill_hash(self, execution_id: str) -> str | None:
        return self.events.get(execution_id)

    def load_position(self, identity: PositionIdentity) -> PositionState | None:
        return self.positions.get(identity.as_tuple())

    def load_position_by_id(self, position_id: UUID) -> PositionState | None:
        for state in self.positions.values():
            if state.position_id == position_id:
                return state
        return None

    def list_positions(
        self, *, strategy_run_id: UUID | None = None, trading_mode: str | None = None
    ) -> list[PositionState]:
        out = []
        for state in self.positions.values():
            if strategy_run_id is not None and state.strategy_run_id != strategy_run_id:
                continue
            if trading_mode is not None and state.trading_mode != trading_mode:
                continue
            out.append(state)
        return out

    def persist_apply(
        self,
        *,
        identity: PositionIdentity,
        state: PositionState,
        event: PositionEventData,
        fill: PositionFill,
    ) -> None:
        if self.fail_next_apply:
            self.fail_next_apply = False
            raise PositionPersistenceError("simulated DB failure")
        # Durable backstop: source_event_id unique constraint.
        if event.execution_id in self.events:
            raise DuplicateApplyError("duplicate apply (unique constraint)")
        if state.position_id is None:
            state = replace(state, position_id=uuid4())
        key = identity.as_tuple()
        self.positions[key] = state
        self.events[event.execution_id] = event.content_hash
        self.applied.append(event)

    def record_conflict(self, fill: PositionFill, original_hash: str) -> None:
        self.conflicts.append(
            {
                "execution_id": fill.execution_id,
                "original_hash": original_hash,
                "conflicting_hash": fill_content_hash(fill),
            }
        )
