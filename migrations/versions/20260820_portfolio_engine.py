"""Portfolio engine: add aggregate columns to portfolio_snapshots

Revision ID: 20260820_portfolio_engine
Revises: 20260820_position_engine
Create Date: 2026-08-20 00:00:00.000000

Adds Phase-12 portfolio aggregate columns (exposure / market value / margin /
position count / status) to ``portfolio_snapshots`` so portfolio facts are
queryable and indexed rather than hidden in an unbounded blob.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260820_portfolio_engine"
down_revision = "20260820_position_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portfolio_snapshots", sa.Column("market_value", sa.Numeric(18, 4), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("gross_exposure", sa.Numeric(18, 4), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("net_exposure", sa.Numeric(18, 4), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("long_exposure", sa.Numeric(18, 4), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("short_exposure", sa.Numeric(18, 4), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("position_count", sa.Integer(), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("available_margin", sa.Numeric(18, 4), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("used_margin", sa.Numeric(18, 4), nullable=True))
    op.add_column("portfolio_snapshots", sa.Column("status", sa.String(length=32), nullable=True))
    op.create_index(
        "ix_portfolio_snapshots_account_mode",
        "portfolio_snapshots",
        ["broker_account_id", "trading_mode"],
    )


def downgrade() -> None:
    op.drop_index("ix_portfolio_snapshots_account_mode", table_name="portfolio_snapshots")
    op.drop_column("portfolio_snapshots", "status")
    op.drop_column("portfolio_snapshots", "used_margin")
    op.drop_column("portfolio_snapshots", "available_margin")
    op.drop_column("portfolio_snapshots", "position_count")
    op.drop_column("portfolio_snapshots", "short_exposure")
    op.drop_column("portfolio_snapshots", "long_exposure")
    op.drop_column("portfolio_snapshots", "net_exposure")
    op.drop_column("portfolio_snapshots", "gross_exposure")
    op.drop_column("portfolio_snapshots", "market_value")
