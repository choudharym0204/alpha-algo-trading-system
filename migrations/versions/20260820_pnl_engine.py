"""P&L engine: pnl_events + pnl_snapshots tables

Revision ID: 20260820_pnl_engine
Revises: 20260820_portfolio_engine
Create Date: 2026-08-20 00:00:00.000000

Adds the append-only realized-P&L accounting ledger (``pnl_events``, one row
per execution identity) and the durable account-scoped P&L read model
(``pnl_snapshots``).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260820_pnl_engine"
down_revision = "20260820_portfolio_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pnl_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trading_mode", sa.String(length=16), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=True),
        sa.Column("average_cost", sa.Numeric(18, 4), nullable=True),
        sa.Column("gross_pnl", sa.Numeric(18, 4), nullable=False),
        sa.Column("costs", sa.Numeric(18, 4), nullable=False),
        sa.Column("net_pnl", sa.Numeric(18, 4), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("execution_id", name="uq_pnl_events_execution_id"),
    )
    op.create_index("ix_pnl_events_account_id", "pnl_events", ["account_id"])
    op.create_index("ix_pnl_events_strategy_run_id", "pnl_events", ["strategy_run_id"])
    op.create_index("ix_pnl_events_position_id", "pnl_events", ["position_id"])
    op.create_index("ix_pnl_events_instrument_id", "pnl_events", ["instrument_id"])

    op.create_table(
        "pnl_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trading_mode", sa.String(length=16), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(18, 4), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(18, 4), nullable=True),
        sa.Column("gross_pnl", sa.Numeric(18, 4), nullable=False),
        sa.Column("costs", sa.Numeric(18, 4), nullable=False),
        sa.Column("net_pnl", sa.Numeric(18, 4), nullable=False),
        sa.Column("position_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "trading_mode", "snapshot_at", name="uq_pnl_snapshots_account_mode_snapshot_at"),
    )
    op.create_index("ix_pnl_snapshots_account_mode", "pnl_snapshots", ["account_id", "trading_mode"])


def downgrade() -> None:
    op.drop_index("ix_pnl_snapshots_account_mode", table_name="pnl_snapshots")
    op.drop_table("pnl_snapshots")
    op.drop_index("ix_pnl_events_instrument_id", table_name="pnl_events")
    op.drop_index("ix_pnl_events_position_id", table_name="pnl_events")
    op.drop_index("ix_pnl_events_strategy_run_id", table_name="pnl_events")
    op.drop_index("ix_pnl_events_account_id", table_name="pnl_events")
    op.drop_table("pnl_events")
