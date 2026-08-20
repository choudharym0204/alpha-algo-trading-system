"""SQLAlchemy portfolio repository (Phase 12).

Durable persistence for ``portfolio_snapshots``. COMMIT is the boundary of
truth; a snapshot write is atomic and idempotent via the existing unique
constraint on ``(broker_account_id, trading_mode, snapshot_at)``.

NOTE: live PostgreSQL verification is deferred (no Docker in this environment);
this repository is exercised through the in-memory test double, with the
model/migration verified by schema tests.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from alpha_algo_portfolio_engine.contracts import (
    PortfolioCompleteness,
    PortfolioComputation,
    PortfolioSnapshot,
    PortfolioStatus,
)
from alpha_algo_portfolio_engine.errors import (
    DuplicateSnapshotError,
    PortfolioPersistenceError,
)
from alpha_algo_shared.db.models.safety import PortfolioSnapshot as OrmPortfolioSnapshot


def _breakdown_payload(c: PortfolioComputation) -> list[dict]:
    return [
        {
            "strategy_run_id": str(b.strategy_run_id),
            "position_count": b.position_count,
            "market_value": str(b.market_value) if b.market_value is not None else None,
            "gross_exposure": str(b.gross_exposure),
        }
        for b in c.strategy_breakdown
    ]


def to_orm(
    *,
    snapshot: PortfolioSnapshot,
    computation: PortfolioComputation,
    content_hash: str,
) -> OrmPortfolioSnapshot:
    payload = {
        "_content_hash": content_hash,
        "_completeness": computation.completeness.value,
        "missing_instrument_ids": [str(i) for i in computation.missing_instrument_ids],
        "stale_instrument_ids": [str(i) for i in computation.stale_instrument_ids],
        "strategy_breakdown": _breakdown_payload(computation),
    }
    return OrmPortfolioSnapshot(
        broker_account_id=snapshot.account_id,
        trading_mode=snapshot.trading_mode,
        snapshot_at=snapshot.snapshot_at,
        equity_value=snapshot.equity_value,
        cash_balance=snapshot.cash_balance,
        market_value=snapshot.market_value,
        gross_exposure=snapshot.gross_exposure,
        net_exposure=snapshot.net_exposure,
        long_exposure=snapshot.long_exposure,
        short_exposure=snapshot.short_exposure,
        position_count=snapshot.position_count,
        available_margin=snapshot.available_margin,
        used_margin=snapshot.used_margin,
        status=snapshot.status.value,
        snapshot_payload=payload,
    )


def from_orm(rec: OrmPortfolioSnapshot) -> PortfolioSnapshot:
    payload = rec.snapshot_payload or {}
    completeness_raw = payload.get("_completeness", PortfolioCompleteness.COMPLETE.value)
    return PortfolioSnapshot(
        snapshot_id=rec.id,
        account_id=rec.broker_account_id,
        trading_mode=rec.trading_mode,
        status=PortfolioStatus((rec.status or PortfolioStatus.UNINITIALIZED.value).upper()),
        completeness=PortfolioCompleteness(completeness_raw),
        position_count=rec.position_count or 0,
        gross_exposure=rec.gross_exposure or Decimal("0"),
        net_exposure=rec.net_exposure or Decimal("0"),
        long_exposure=rec.long_exposure or Decimal("0"),
        short_exposure=rec.short_exposure or Decimal("0"),
        market_value=rec.market_value,
        cash_balance=rec.cash_balance,
        equity_value=rec.equity_value,
        available_margin=rec.available_margin,
        used_margin=rec.used_margin,
        snapshot_at=rec.snapshot_at,
    )


class PortfolioRepository:
    """SQLAlchemy-backed portfolio snapshot store (implements the engine protocol)."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def save_snapshot(
        self,
        *,
        snapshot: PortfolioSnapshot,
        computation: PortfolioComputation,
        content_hash: str,
    ) -> PortfolioSnapshot:
        session = self._session_factory()
        try:
            row = to_orm(
                snapshot=snapshot, computation=computation, content_hash=content_hash
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return from_orm(row)
        except IntegrityError as exc:
            session.rollback()
            raise DuplicateSnapshotError(
                "duplicate snapshot (unique constraint)"
            ) from exc
        except DuplicateSnapshotError:
            session.rollback()
            raise
        except Exception as exc:
            session.rollback()
            raise PortfolioPersistenceError("portfolio snapshot write failed") from exc
        finally:
            session.close()

    def load_snapshot(
        self, *, account_id: UUID, trading_mode: str, snapshot_at: datetime
    ) -> PortfolioSnapshot | None:
        session = self._session_factory()
        try:
            rec = session.execute(
                select(OrmPortfolioSnapshot).where(
                    OrmPortfolioSnapshot.broker_account_id == account_id,
                    OrmPortfolioSnapshot.trading_mode == trading_mode.upper(),
                    OrmPortfolioSnapshot.snapshot_at == snapshot_at,
                )
            ).scalar_one_or_none()
            return from_orm(rec) if rec is not None else None
        finally:
            session.close()

    def load_latest(
        self, *, account_id: UUID, trading_mode: str
    ) -> PortfolioSnapshot | None:
        session = self._session_factory()
        try:
            rec = session.execute(
                select(OrmPortfolioSnapshot)
                .where(
                    OrmPortfolioSnapshot.broker_account_id == account_id,
                    OrmPortfolioSnapshot.trading_mode == trading_mode.upper(),
                )
                .order_by(OrmPortfolioSnapshot.snapshot_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            return from_orm(rec) if rec is not None else None
        finally:
            session.close()

    def list_snapshots(
        self, *, account_id: UUID, trading_mode: str, limit: int = 100
    ) -> list[PortfolioSnapshot]:
        session = self._session_factory()
        try:
            recs = session.execute(
                select(OrmPortfolioSnapshot)
                .where(
                    OrmPortfolioSnapshot.broker_account_id == account_id,
                    OrmPortfolioSnapshot.trading_mode == trading_mode.upper(),
                )
                .order_by(OrmPortfolioSnapshot.snapshot_at.desc())
                .limit(limit)
            ).scalars().all()
            return [from_orm(rec) for rec in recs]
        finally:
            session.close()
