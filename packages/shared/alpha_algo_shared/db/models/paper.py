"""Paper trading persistence models (Phase 15).

Paper-specific durable state only — runs, accounts, and the funds ledger. Paper
orders/executions/positions already persist through the existing Phase 8/9/11
tables; these models deliberately do **not** duplicate that storage.

- ``PaperRun``      — one row per paper run (identity + config fingerprint + status).
- ``PaperAccount``  — PAPER-labeled account (starting capital + run + status).
- ``PaperFunds``    — current cash/reserve ledger per account (upserted, one row).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from alpha_algo_shared.db.base import Base, TimestampMixin


class PaperRun(TimestampMixin, Base):
    __tablename__ = "paper_runs"
    __table_args__ = (
        Index("ix_paper_runs_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperAccount(TimestampMixin, Base):
    __tablename__ = "paper_accounts"
    __table_args__ = (
        Index("ix_paper_accounts_paper_run_id", "paper_run_id"),
        Index("ix_paper_accounts_status", "status"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    paper_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("paper_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trading_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="PAPER")
    starting_capital: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaperFunds(TimestampMixin, Base):
    __tablename__ = "paper_funds"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_paper_funds_account_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("paper_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    available_cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    reserved_cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
