"""P&L Engine persistence models (Phase 13).

``PnlEvent`` — append-only accounting facts (one per execution identity).
``PnlSnapshot`` — durable account-scoped P&L read model.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from alpha_algo_shared.db.base import Base, TimestampMixin


class PnlEvent(TimestampMixin, Base):
    __tablename__ = "pnl_events"
    __table_args__ = (
        UniqueConstraint("execution_id", name="uq_pnl_events_execution_id"),
        Index("ix_pnl_events_account_id", "account_id"),
        Index("ix_pnl_events_strategy_run_id", "strategy_run_id"),
        Index("ix_pnl_events_position_id", "position_id"),
        Index("ix_pnl_events_instrument_id", "instrument_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    strategy_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    position_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("positions.id", ondelete="SET NULL"),
        nullable=True,
    )
    trading_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    average_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    gross_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    costs: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    net_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)


class PnlSnapshot(TimestampMixin, Base):
    __tablename__ = "pnl_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "trading_mode",
            "snapshot_at",
            name="uq_pnl_snapshots_account_mode_snapshot_at",
        ),
        Index("ix_pnl_snapshots_account_mode", "account_id", "trading_mode"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    strategy_run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    trading_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    gross_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    costs: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    net_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
