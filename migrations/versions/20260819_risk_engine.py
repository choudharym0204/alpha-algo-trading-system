"""risk engine: decision_id + provenance + approval-binding columns on risk_events

Revision ID: 20260819_risk_engine
Revises: 20260819_signal_engine
Create Date: 2026-08-19 00:00:00.000000

Note: ``decision_id`` is added NOT NULL without server_default. This is safe
because the ``risk_events`` table is empty at this migration point — Phase 6 is
the FIRST writer (all prior phases left risk evaluation un-wired), so no
pre-existing risk rows can exist. ``decision_id`` is row-unique and has no
meaningful default.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260819_risk_engine"
down_revision = "20260819_signal_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "risk_events",
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_unique_constraint("uq_risk_events_decision_id", "risk_events", ["decision_id"])
    op.add_column(
        "risk_events",
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "risk_events",
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("risk_events", sa.Column("trading_mode", sa.String(length=16), nullable=True))
    op.add_column("risk_events", sa.Column("rule_id", sa.String(length=100), nullable=True))
    op.add_column("risk_events", sa.Column("binding_hash", sa.String(length=128), nullable=True))
    op.add_column("risk_events", sa.Column("identity_key", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_risk_events_identity_key", "risk_events", ["identity_key"])
    op.add_column(
        "risk_events",
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("risk_events", "snapshot_id")
    op.drop_constraint("uq_risk_events_identity_key", "risk_events", type_="unique")
    op.drop_column("risk_events", "identity_key")
    op.drop_column("risk_events", "binding_hash")
    op.drop_column("risk_events", "rule_id")
    op.drop_column("risk_events", "trading_mode")
    op.drop_column("risk_events", "account_id")
    op.drop_column("risk_events", "strategy_id")
    op.drop_constraint("uq_risk_events_decision_id", "risk_events", type_="unique")
    op.drop_column("risk_events", "decision_id")
