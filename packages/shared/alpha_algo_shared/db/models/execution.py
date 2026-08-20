"""Execution attempt persistence model (Phase 9).

A durable record per submission attempt (order-scoped, retry-aware). One order
can have multiple attempts (execution_id stable, attempt_number advances); the
unique constraint prevents duplicate attempts for the same (execution, attempt).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from alpha_algo_shared.db.base import Base, TimestampMixin


class ExecutionAttemptRecord(TimestampMixin, Base):
    __tablename__ = "execution_attempts"
    __table_args__ = (
        UniqueConstraint(
            "execution_id",
            "attempt_number",
            name="uq_execution_attempts_execution_id_attempt_number",
        ),
        Index("ix_execution_attempts_order_id", "order_id"),
        Index("ix_execution_attempts_state", "state"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
