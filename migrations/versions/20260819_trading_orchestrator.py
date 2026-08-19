"""trading orchestrator: trading_intents table

Revision ID: 20260819_trading_orchestrator
Revises: 20260819_risk_engine
Create Date: 2026-08-19 00:00:00.000000

Adds the ``trading_intents`` table — the durable OMS-ready intent produced by the
Phase-7 orchestrator. ``orchestration_id`` is unique (idempotency backstop); it is
a deterministic hash, not a random UUID. The table is a new coordination-layer
artifact, distinct from ``signals`` (Phase 5), ``risk_events`` (Phase 6), and the
future ``orders`` (Phase 8); it does not duplicate them.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260819_trading_orchestrator"
down_revision = "20260819_risk_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trading_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("orchestration_id", sa.String(length=64), nullable=False),
        sa.Column("correlation_id", sa.String(length=100), nullable=True),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("strategy_version", sa.String(length=64), nullable=True),
        sa.Column("strategy_config_hash", sa.String(length=128), nullable=True),
        sa.Column("strategy_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=True),
        sa.Column("order_type", sa.String(length=16), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("limit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("trading_mode", sa.String(length=16), nullable=True),
        sa.Column("risk_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_id", sa.String(length=100), nullable=True),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("binding_hash", sa.String(length=128), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False, server_default=sa.text("'received'")),
        sa.Column("reason_code", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("intent_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint(
        "uq_trading_intents_orchestration_id", "trading_intents", ["orchestration_id"]
    )
    op.create_unique_constraint(
        "uq_trading_intents_approval_id", "trading_intents", ["approval_id"]
    )
    op.create_foreign_key(
        "fk_trading_intents_signal_id",
        "trading_intents",
        "signals",
        ["signal_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_trading_intents_instrument_id",
        "trading_intents",
        "instruments",
        ["instrument_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_trading_intents_strategy_run_id",
        "trading_intents",
        "strategy_runs",
        ["strategy_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_trading_intents_signal_id", "trading_intents", ["signal_id"]
    )
    op.create_index(
        "ix_trading_intents_strategy_id", "trading_intents", ["strategy_id"]
    )
    op.create_index(
        "ix_trading_intents_state", "trading_intents", ["state"]
    )


def downgrade() -> None:
    op.drop_index("ix_trading_intents_state", table_name="trading_intents")
    op.drop_index("ix_trading_intents_strategy_id", table_name="trading_intents")
    op.drop_index("ix_trading_intents_signal_id", table_name="trading_intents")
    op.drop_constraint(
        "fk_trading_intents_strategy_run_id", "trading_intents", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_trading_intents_instrument_id", "trading_intents", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_trading_intents_signal_id", "trading_intents", type_="foreignkey"
    )
    op.drop_constraint(
        "uq_trading_intents_approval_id", "trading_intents", type_="unique"
    )
    op.drop_constraint(
        "uq_trading_intents_orchestration_id", "trading_intents", type_="unique"
    )
    op.drop_table("trading_intents")
