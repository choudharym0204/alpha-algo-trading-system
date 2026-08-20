"""Reconciliation Engine persistence models (Phase 14).

``ReconciliationRun`` — one row per reconciliation run (scope, status, counts).
``ReconciliationDiscrepancy`` — append-only evidence, unique by deterministic
``discrepancy_key`` (idempotency backstop).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from alpha_algo_shared.db.base import Base, TimestampMixin


class ReconciliationRun(TimestampMixin, Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        Index("ix_reconciliation_runs_account_id", "account_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    broker: Mapped[str] = mapped_column(String(32), nullable=False)
    trading_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mismatched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    internal_only: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    broker_only: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unavailable: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflicts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReconciliationDiscrepancy(TimestampMixin, Base):
    __tablename__ = "reconciliation_discrepancies"
    __table_args__ = (
        UniqueConstraint("discrepancy_key", name="uq_reconciliation_discrepancies_key"),
        Index("ix_reconciliation_discrepancies_run_id", "run_id"),
        Index("ix_reconciliation_discrepancies_account_id", "account_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    discrepancy_key: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("reconciliation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    broker: Mapped[str] = mapped_column(String(32), nullable=False)
    trading_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    internal_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    broker_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(32), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
