"""Position engine: add positions.last_execution_id

Revision ID: 20260820_position_engine
Revises: 20260819_execution
Create Date: 2026-08-20 00:00:00.000000

Adds the Phase-11 ``last_execution_id`` column to ``positions`` — the durable
execution identity of the last applied fill (a restart/reconciliation reference,
not a financial field).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260820_position_engine"
down_revision = "20260819_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "positions",
        sa.Column("last_execution_id", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("positions", "last_execution_id")
