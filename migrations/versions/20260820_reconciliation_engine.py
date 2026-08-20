"""Reconciliation engine: reconciliation_runs + reconciliation_discrepancies

Revision ID: 20260820_reconciliation_engine
Revises: 20260820_pnl_engine
Create Date: 2026-08-20 00:00:00.000000

Adds the durable reconciliation run record and the append-only discrepancy
evidence ledger (unique by deterministic ``discrepancy_key``).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260820_reconciliation_engine"
down_revision = "20260820_pnl_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("broker", sa.String(length=32), nullable=False),
        sa.Column("trading_mode", sa.String(length=16), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matched", sa.Integer(), nullable=False),
        sa.Column("mismatched", sa.Integer(), nullable=False),
        sa.Column("internal_only", sa.Integer(), nullable=False),
        sa.Column("broker_only", sa.Integer(), nullable=False),
        sa.Column("unknown", sa.Integer(), nullable=False),
        sa.Column("unavailable", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("conflicts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reconciliation_runs_account_id", "reconciliation_runs", ["account_id"])

    op.create_table(
        "reconciliation_discrepancies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discrepancy_key", sa.String(length=128), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("broker", sa.String(length=32), nullable=False),
        sa.Column("trading_mode", sa.String(length=16), nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("internal_state", sa.JSON(), nullable=False),
        sa.Column("broker_state", sa.JSON(), nullable=False),
        sa.Column("resolution_status", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["run_id"], ["reconciliation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("discrepancy_key", name="uq_reconciliation_discrepancies_key"),
    )
    op.create_index("ix_reconciliation_discrepancies_run_id", "reconciliation_discrepancies", ["run_id"])
    op.create_index("ix_reconciliation_discrepancies_account_id", "reconciliation_discrepancies", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_reconciliation_discrepancies_account_id", table_name="reconciliation_discrepancies")
    op.drop_index("ix_reconciliation_discrepancies_run_id", table_name="reconciliation_discrepancies")
    op.drop_table("reconciliation_discrepancies")
    op.drop_index("ix_reconciliation_runs_account_id", table_name="reconciliation_runs")
    op.drop_table("reconciliation_runs")
