"""SQLAlchemy reconciliation repository (Phase 14).

Durable persistence for ``reconciliation_runs`` and
``reconciliation_discrepancies``. The unique ``discrepancy_key`` is the
idempotency backstop; evidence is append-only (no update/delete path).

NOTE: live PostgreSQL verification is deferred (no Docker in this environment);
exercised through the in-memory test double + schema tests.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from alpha_algo_reconciliation_engine.contracts import (
    Discrepancy,
    DiscrepancyKind,
    EntityType,
    ReconciliationRun,
    ResolutionStatus,
    RunStatus,
    Severity,
)
from alpha_algo_reconciliation_engine.errors import (
    DuplicateDiscrepancyError,
    ReconciliationPersistenceError,
)
from alpha_algo_shared.db.models.reconciliation import (
    ReconciliationDiscrepancy as OrmDiscrepancy,
    ReconciliationRun as OrmRun,
)


def to_orm_run(run: ReconciliationRun) -> OrmRun:
    return OrmRun(
        id=run.run_id,
        account_id=run.account_id,
        broker=run.broker,
        trading_mode=run.trading_mode,
        scope=run.scope,
        status=run.status.value,
        started_at=run.started_at,
        completed_at=run.completed_at,
        matched=run.matched,
        mismatched=run.mismatched,
        internal_only=run.internal_only,
        broker_only=run.broker_only,
        unknown=run.unknown,
        unavailable=run.unavailable,
        skipped=run.skipped,
        conflicts=run.conflicts,
        error=run.error,
    )


def from_orm_run(rec: OrmRun) -> ReconciliationRun:
    return ReconciliationRun(
        run_id=rec.id,
        account_id=rec.account_id,
        broker=rec.broker,
        trading_mode=rec.trading_mode,
        scope=rec.scope,
        status=RunStatus(rec.status),
        started_at=rec.started_at,
        completed_at=rec.completed_at,
        matched=rec.matched,
        mismatched=rec.mismatched,
        internal_only=rec.internal_only,
        broker_only=rec.broker_only,
        unknown=rec.unknown,
        unavailable=rec.unavailable,
        skipped=rec.skipped,
        conflicts=rec.conflicts,
        error=rec.error,
    )


def to_orm_discrepancy(d: Discrepancy) -> OrmDiscrepancy:
    return OrmDiscrepancy(
        discrepancy_key=d.discrepancy_key,
        run_id=d.run_id,
        account_id=d.account_id,
        broker=d.broker,
        trading_mode=d.trading_mode,
        entity_type=d.entity_type.value,
        entity_id=d.entity_id,
        kind=d.kind.value,
        severity=d.severity.value,
        internal_state=d.internal_state,
        broker_state=d.broker_state,
        resolution_status=d.resolution_status.value,
        content_hash=d.content_hash,
        observed_at=d.observed_at,
    )


def from_orm_discrepancy(rec: OrmDiscrepancy) -> Discrepancy:
    return Discrepancy(
        id=rec.id,
        discrepancy_key=rec.discrepancy_key,
        run_id=rec.run_id,
        account_id=rec.account_id,
        broker=rec.broker,
        trading_mode=rec.trading_mode,
        entity_type=EntityType(rec.entity_type),
        entity_id=rec.entity_id,
        kind=DiscrepancyKind(rec.kind),
        severity=Severity(rec.severity),
        internal_state=rec.internal_state or {},
        broker_state=rec.broker_state or {},
        resolution_status=ResolutionStatus(rec.resolution_status),
        content_hash=rec.content_hash,
        observed_at=rec.observed_at,
    )


class ReconciliationRepository:
    """SQLAlchemy-backed reconciliation store (implements the engine protocol)."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def save_run(self, *, run: ReconciliationRun) -> ReconciliationRun:
        session = self._session_factory()
        try:
            row = to_orm_run(run)
            session.add(row)
            session.commit()
            session.refresh(row)
            return from_orm_run(row)
        except Exception as exc:
            session.rollback()
            raise ReconciliationPersistenceError("reconciliation run write failed") from exc
        finally:
            session.close()

    def load_run(self, run_id: UUID) -> ReconciliationRun | None:
        session = self._session_factory()
        try:
            rec = session.get(OrmRun, run_id)
            return from_orm_run(rec) if rec is not None else None
        finally:
            session.close()

    def save_discrepancy(self, *, discrepancy: Discrepancy) -> Discrepancy:
        session = self._session_factory()
        try:
            row = to_orm_discrepancy(discrepancy)
            session.add(row)
            session.commit()
            session.refresh(row)
            return from_orm_discrepancy(row)
        except IntegrityError as exc:
            session.rollback()
            raise DuplicateDiscrepancyError(
                f"duplicate discrepancy {discrepancy.discrepancy_key}"
            ) from exc
        except DuplicateDiscrepancyError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise ReconciliationPersistenceError("discrepancy write failed") from exc
        finally:
            session.close()

    def load_discrepancy(self, discrepancy_key: str) -> Discrepancy | None:
        session = self._session_factory()
        try:
            rec = session.execute(
                select(OrmDiscrepancy).where(OrmDiscrepancy.discrepancy_key == discrepancy_key)
            ).scalar_one_or_none()
            return from_orm_discrepancy(rec) if rec is not None else None
        finally:
            session.close()

    def list_discrepancies(
        self, *, run_id: UUID | None = None, account_id: UUID | None = None
    ) -> list[Discrepancy]:
        session = self._session_factory()
        try:
            stmt = select(OrmDiscrepancy)
            if run_id is not None:
                stmt = stmt.where(OrmDiscrepancy.run_id == run_id)
            if account_id is not None:
                stmt = stmt.where(OrmDiscrepancy.account_id == account_id)
            stmt = stmt.order_by(OrmDiscrepancy.created_at)
            recs = session.execute(stmt).scalars().all()
            return [from_orm_discrepancy(rec) for rec in recs]
        finally:
            session.close()
