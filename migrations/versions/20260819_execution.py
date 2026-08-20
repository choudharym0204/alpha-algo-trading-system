"""Execution: add execution_attempts table

Revision ID: 20260819_execution
Revises: 20260819_oms
Create Date: 2026-08-19 00:00:00.000000

Adds the Phase-9 ``execution_attempts`` table — one durable row per submission
attempt (order-scoped, retry-aware). ``execution_id`` is deterministic per order;
``attempt_number`` advances on bounded retries; the unique constraint prevents
duplicate attempts for the same (execution_id, attempt_number).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260819_execution"
down_revision = "20260819_oms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("broker_order_id", sa.String(length=100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_id",
            "attempt_number",
            name="uq_execution_attempts_execution_id_attempt_number",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_execution_attempts_order_id", "execution_attempts", ["order_id"]
    )
    op.create_index("ix_execution_attempts_state", "execution_attempts", ["state"])


def downgrade() -> None:
    op.drop_index("ix_execution_attempts_state", table_name="execution_attempts")
    op.drop_index("ix_execution_attempts_order_id", table_name="execution_attempts")
    op.drop_table("execution_attempts")
