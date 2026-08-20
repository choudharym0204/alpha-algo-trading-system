"""SQLAlchemy position repository (Phase 11).

Durable persistence for positions (`positions`) and append-only position events
(`position_events`). COMMIT is the boundary of truth; every fill application is
atomic (position row + event row in one transaction) and keyed on a stable
``execution_id`` stored in ``PositionEvent.source_event_id`` for idempotency.

Concurrency model:
* In-process — the engine serializes per-position via a keyed lock.
* Cross-process — ``SELECT ... FOR UPDATE`` row-locks the position row, and the
  ``source_event_id`` + position-key unique constraints are the durable backstop.

NOTE: live PostgreSQL verification is deferred (no Docker in this environment);
this repository is exercised through the in-memory test double, with the
model/migration verified by schema tests.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from alpha_algo_position_engine.contracts import (
    PositionEventType,
    PositionFill,
    PositionIdentity,
    PositionState,
    PositionStatus,
)
from alpha_algo_position_engine.engine import PositionEventData
from alpha_algo_position_engine.errors import (
    DuplicateApplyError,
    PositionPersistenceError,
)
from alpha_algo_shared.db.models.safety import PositionEvent
from alpha_algo_shared.db.models.trading import Position


def _position_where(identity: PositionIdentity):
    return (
        Position.strategy_run_id == identity.strategy_run_id,
        Position.instrument_id == identity.instrument_id,
        Position.trading_mode == identity.trading_mode,
    )


def to_state(rec: Position | None) -> PositionState | None:
    if rec is None:
        return None
    return PositionState(
        position_id=rec.id,
        strategy_run_id=rec.strategy_run_id,
        instrument_id=rec.instrument_id,
        trading_mode=rec.trading_mode,
        account_id=rec.broker_account_id,
        quantity=rec.quantity,
        average_price=rec.average_price,
        status=PositionStatus((rec.status or "FLAT").upper()),
        opened_at=rec.opened_at,
        closed_at=rec.closed_at,
        last_execution_id=rec.last_execution_id,
    )


class PositionRepository:
    """SQLAlchemy-backed position state store (implements the engine protocol)."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    # -------------------------------------------------------------- dedup / read
    def find_fill_hash(self, execution_id: str) -> str | None:
        session = self._session_factory()
        try:
            rec = session.execute(
                select(PositionEvent).where(
                    PositionEvent.source_event_id == execution_id
                )
            ).scalar_one_or_none()
            if rec is None or rec.event_payload is None:
                return None
            return rec.event_payload.get("_content_hash")
        finally:
            session.close()

    def load_position(self, identity: PositionIdentity) -> PositionState | None:
        session = self._session_factory()
        try:
            rec = session.execute(
                select(Position).where(*_position_where(identity))
            ).scalar_one_or_none()
            return to_state(rec)
        finally:
            session.close()

    def load_position_by_id(self, position_id: UUID) -> PositionState | None:
        session = self._session_factory()
        try:
            return to_state(session.get(Position, position_id))
        finally:
            session.close()

    def list_positions(
        self, *, strategy_run_id: UUID | None = None, trading_mode: str | None = None
    ) -> list[PositionState]:
        session = self._session_factory()
        try:
            stmt = select(Position)
            if strategy_run_id is not None:
                stmt = stmt.where(Position.strategy_run_id == strategy_run_id)
            if trading_mode is not None:
                stmt = stmt.where(Position.trading_mode == trading_mode)
            return [to_state(rec) for rec in session.execute(stmt).scalars().all()]
        finally:
            session.close()

    # ------------------------------------------------------------------- apply
    def persist_apply(
        self,
        *,
        identity: PositionIdentity,
        state: PositionState,
        event: PositionEventData,
        fill: PositionFill,
    ) -> None:
        session = self._session_factory()
        try:
            position = session.execute(
                select(Position)
                .where(*_position_where(identity))
                .with_for_update()
            ).scalar_one_or_none()

            if position is None:
                position = self._new_position_row(state)
                session.add(position)
                session.flush()
            else:
                self._apply_state(position, state)

            session.add(self._new_event_row(position.id, event))
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            # The durable source_event_id / position-key backstop fired: the fill
            # was already applied (or the position was concurrently created).
            raise DuplicateApplyError(
                "duplicate apply (unique constraint)"
            ) from exc
        except DuplicateApplyError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise PositionPersistenceError("position apply failed") from exc
        finally:
            session.close()

    def record_conflict(self, fill: PositionFill, original_hash: str) -> None:
        """Append-only conflict evidence (never rewrites the original event)."""
        from alpha_algo_position_engine.identity import fill_content_hash

        session = self._session_factory()
        try:
            # Resolve the position the original fill created (via the event).
            original = session.execute(
                select(PositionEvent).where(
                    PositionEvent.source_event_id == fill.execution_id
                )
            ).scalar_one_or_none()
            position_id = original.position_id if original is not None else None
            if position_id is None:
                # Fallback: locate by identity (the original apply created it).
                rec = session.execute(
                    select(Position).where(*_position_where(
                        PositionIdentity(
                            strategy_run_id=fill.strategy_run_id,
                            instrument_id=fill.instrument_id,
                            trading_mode=fill.trading_mode,
                        )
                    ))
                ).scalar_one_or_none()
                position_id = rec.id if rec is not None else None

            if position_id is None:
                return  # no position to attach evidence to (edge race); conflict still raised

            session.add(
                PositionEvent(
                    position_id=position_id,
                    source_event_id=f"conflict-{fill.execution_id}",
                    event_type=PositionEventType.POSITION_CONFLICT.value,
                    quantity_before=0,
                    quantity_after=0,
                    event_timestamp=fill.occurred_at,
                    reason="same execution identity, different payload",
                    event_payload={
                        "execution_id": fill.execution_id,
                        "original_hash": original_hash,
                        "conflicting_hash": fill_content_hash(fill),
                        "side": fill.side,
                        "quantity": str(fill.quantity),
                        "price": str(fill.price),
                    },
                )
            )
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    # ---------------------------------------------------------------- builders
    @staticmethod
    def _new_position_row(state: PositionState) -> Position:
        return Position(
            id=state.position_id or uuid4(),
            strategy_run_id=state.strategy_run_id,
            instrument_id=state.instrument_id,
            trading_mode=state.trading_mode,
            broker_account_id=state.account_id,
            quantity=state.quantity,
            average_price=state.average_price,
            opened_at=state.opened_at,
            closed_at=state.closed_at,
            status=state.status.value,
            last_execution_id=state.last_execution_id,
        )

    @staticmethod
    def _apply_state(position: Position, state: PositionState) -> None:
        position.broker_account_id = state.account_id
        position.quantity = state.quantity
        position.average_price = state.average_price
        position.opened_at = state.opened_at
        position.closed_at = state.closed_at
        position.status = state.status.value
        position.last_execution_id = state.last_execution_id

    @staticmethod
    def _new_event_row(position_id: UUID, event: PositionEventData) -> PositionEvent:
        return PositionEvent(
            position_id=position_id,
            source_event_id=event.execution_id,
            event_type=event.event_type.value,
            quantity_before=event.quantity_before,
            quantity_after=event.quantity_after,
            event_timestamp=event.occurred_at,
            reason=event.reason,
            event_payload={"_content_hash": event.content_hash},
        )
