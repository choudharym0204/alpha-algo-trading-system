"""Paper trading: paper_runs + paper_accounts + paper_funds

Revision ID: 20260820_paper_trading
Revises: 20260820_reconciliation_engine
Create Date: 2026-08-20 00:00:00.000000

Adds the paper-specific durable baseline (run identity, PAPER-labeled account,
and the cash/reserve funds ledger). Paper orders/executions/positions already
persist via the Phase 8/9/11 tables, so no duplicate storage is created.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260820_paper_trading"
down_revision = "20260820_reconciliation_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_runs_status", "paper_runs", ["status"])

    op.create_table(
        "paper_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trading_mode", sa.String(length=16), nullable=False),
        sa.Column("starting_capital", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["paper_run_id"], ["paper_runs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_accounts_paper_run_id", "paper_accounts", ["paper_run_id"])
    op.create_index("ix_paper_accounts_status", "paper_accounts", ["status"])

    op.create_table(
        "paper_funds",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("available_cash", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("reserved_cash", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["account_id"], ["paper_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_paper_funds_account_id"),
    )


def downgrade() -> None:
    op.drop_table("paper_funds")
    op.drop_index("ix_paper_accounts_status", table_name="paper_accounts")
    op.drop_index("ix_paper_accounts_paper_run_id", table_name="paper_accounts")
    op.drop_table("paper_accounts")
    op.drop_index("ix_paper_runs_status", table_name="paper_runs")
    op.drop_table("paper_runs")
