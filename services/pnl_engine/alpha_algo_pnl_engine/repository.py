"""SQLAlchemy P&L repository (Phase 13).

Durable persistence for ``pnl_events`` (append-only realized facts) and
``pnl_snapshots`` (account-scoped read model). COMMIT is the boundary of truth;
the unique constraint on ``execution_id`` is the durable idempotency backstop.

NOTE: live PostgreSQL verification is deferred (no Docker in this environment);
exercised through the in-memory test double + schema tests.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from alpha_algo_pnl_engine.contracts import (
    PnlEvent,
    PnlEventType,
    PnlSnapshot,
    PnlStatus,
)
from alpha_algo_pnl_engine.errors import (
    DuplicateExecutionError,
    PnlPersistenceError,
)
from alpha_algo_shared.db.models.pnl import (
    PnlEvent as OrmPnlEvent,
    PnlSnapshot as OrmPnlSnapshot,
)


def to_orm_event(event: PnlEvent) -> OrmPnlEvent:
    return OrmPnlEvent(
        execution_id=event.execution_id,
        event_type=event.event_type.value,
        account_id=event.account_id,
        strategy_run_id=event.strategy_run_id,
        instrument_id=event.instrument_id,
        position_id=event.position_id,
        trading_mode=event.trading_mode,
        side=event.side,
        quantity=event.quantity,
        price=event.price,
        average_cost=event.average_cost,
        gross_pnl=event.gross_pnl,
        costs=event.costs,
        net_pnl=event.net_pnl,
        occurred_at=event.occurred_at,
        content_hash=event.content_hash,
    )


def from_orm_event(rec: OrmPnlEvent) -> PnlEvent:
    return PnlEvent(
        id=rec.id,
        execution_id=rec.execution_id,
        event_type=PnlEventType(rec.event_type),
        account_id=rec.account_id,
        strategy_run_id=rec.strategy_run_id,
        instrument_id=rec.instrument_id,
        position_id=rec.position_id,
        trading_mode=rec.trading_mode,
        side=rec.side,
        quantity=rec.quantity,
        price=rec.price,
        average_cost=rec.average_cost,
        gross_pnl=rec.gross_pnl,
        costs=rec.costs,
        net_pnl=rec.net_pnl,
        occurred_at=rec.occurred_at,
        content_hash=rec.content_hash,
    )


def to_orm_snapshot(snap: PnlSnapshot) -> OrmPnlSnapshot:
    return OrmPnlSnapshot(
        account_id=snap.account_id,
        trading_mode=snap.trading_mode,
        snapshot_at=snap.snapshot_at,
        realized_pnl=snap.realized_pnl,
        unrealized_pnl=snap.unrealized_pnl,
        gross_pnl=snap.gross_pnl,
        costs=snap.costs,
        net_pnl=snap.net_pnl,
        position_count=snap.position_count,
        status=snap.status.value,
    )


def from_orm_snapshot(rec: OrmPnlSnapshot) -> PnlSnapshot:
    return PnlSnapshot(
        snapshot_id=rec.id,
        account_id=rec.account_id,
        trading_mode=rec.trading_mode,
        snapshot_at=rec.snapshot_at,
        realized_pnl=rec.realized_pnl,
        unrealized_pnl=rec.unrealized_pnl,
        gross_pnl=rec.gross_pnl,
        costs=rec.costs,
        net_pnl=rec.net_pnl,
        position_count=rec.position_count,
        status=PnlStatus(rec.status),
    )


class PnlRepository:
    """SQLAlchemy-backed P&L store (implements the engine protocol)."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def save_event(self, *, event: PnlEvent) -> PnlEvent:
        session = self._session_factory()
        try:
            row = to_orm_event(event)
            session.add(row)
            session.commit()
            session.refresh(row)
            return from_orm_event(row)
        except IntegrityError as exc:
            session.rollback()
            raise DuplicateExecutionError(
                f"duplicate P&L event for execution {event.execution_id}"
            ) from exc
        except DuplicateExecutionError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise PnlPersistenceError("P&L event write failed") from exc
        finally:
            session.close()

    def load_event(self, execution_id: str) -> PnlEvent | None:
        session = self._session_factory()
        try:
            rec = session.execute(
                select(OrmPnlEvent).where(OrmPnlEvent.execution_id == execution_id)
            ).scalar_one_or_none()
            return from_orm_event(rec) if rec is not None else None
        finally:
            session.close()

    def list_events(
        self,
        *,
        account_id: UUID | None = None,
        strategy_run_id: UUID | None = None,
        instrument_id: UUID | None = None,
        position_id: UUID | None = None,
    ) -> list[PnlEvent]:
        session = self._session_factory()
        try:
            stmt = select(OrmPnlEvent)
            if account_id is not None:
                stmt = stmt.where(OrmPnlEvent.account_id == account_id)
            if strategy_run_id is not None:
                stmt = stmt.where(OrmPnlEvent.strategy_run_id == strategy_run_id)
            if instrument_id is not None:
                stmt = stmt.where(OrmPnlEvent.instrument_id == instrument_id)
            if position_id is not None:
                stmt = stmt.where(OrmPnlEvent.position_id == position_id)
            stmt = stmt.order_by(OrmPnlEvent.occurred_at)
            recs = session.execute(stmt).scalars().all()
            return [from_orm_event(rec) for rec in recs]
        finally:
            session.close()

    def realized_pnl_for_position(self, *, position_id: UUID) -> Decimal:
        session = self._session_factory()
        try:
            total = session.execute(
                select(func.coalesce(func.sum(OrmPnlEvent.net_pnl), 0)).where(
                    OrmPnlEvent.position_id == position_id,
                    OrmPnlEvent.event_type == PnlEventType.REALIZED_PNL.value,
                )
            ).scalar_one()
            return Decimal(total)
        finally:
            session.close()

    def save_snapshot(self, *, snapshot: PnlSnapshot) -> PnlSnapshot:
        session = self._session_factory()
        try:
            row = to_orm_snapshot(snapshot)
            session.add(row)
            session.commit()
            session.refresh(row)
            return from_orm_snapshot(row)
        except IntegrityError as exc:
            session.rollback()
            raise DuplicateExecutionError("duplicate P&L snapshot") from exc
        except DuplicateExecutionError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise PnlPersistenceError("P&L snapshot write failed") from exc
        finally:
            session.close()

    def load_snapshot(
        self, *, account_id: UUID, trading_mode: str, snapshot_at: datetime
    ) -> PnlSnapshot | None:
        session = self._session_factory()
        try:
            rec = session.execute(
                select(OrmPnlSnapshot).where(
                    OrmPnlSnapshot.account_id == account_id,
                    OrmPnlSnapshot.trading_mode == trading_mode.upper(),
                    OrmPnlSnapshot.snapshot_at == snapshot_at,
                )
            ).scalar_one_or_none()
            return from_orm_snapshot(rec) if rec is not None else None
        finally:
            session.close()

    def load_latest_snapshot(
        self, *, account_id: UUID, trading_mode: str
    ) -> PnlSnapshot | None:
        session = self._session_factory()
        try:
            rec = session.execute(
                select(OrmPnlSnapshot)
                .where(
                    OrmPnlSnapshot.account_id == account_id,
                    OrmPnlSnapshot.trading_mode == trading_mode.upper(),
                )
                .order_by(OrmPnlSnapshot.snapshot_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            return from_orm_snapshot(rec) if rec is not None else None
        finally:
            session.close()
