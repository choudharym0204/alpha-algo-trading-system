"""signal engine: provenance + idempotency + state columns on signals

Revision ID: 20260819_signal_engine
Revises: 20260812_timescale_market_data
Create Date: 2026-08-19 00:00:00.000000

Note: the new provenance columns are added NOT NULL without server_default.
This is safe because the ``signals`` table is empty at this migration point:
Phase 5 is the FIRST writer to the table (all prior phases persist to other
tables) and LIVE is fail-closed, so no pre-existing signal rows can exist.
``identity_key``/``content_hash`` are row-unique and have no meaningful default.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260819_signal_engine"
down_revision = "20260812_timescale_market_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. The relational FKs become nullable: Phase 5 records runtime provenance
    #    (strategy_id / strategy_version / config_hash / code_hash / run_id)
    #    directly on the signal; the FK rows are populated by a later phase.
    op.drop_constraint("fk_signals_strategy_run_id_strategy_runs", "signals", type_="foreignkey")
    op.drop_constraint("fk_signals_strategy_version_id_strategy_versions", "signals", type_="foreignkey")
    op.alter_column(
        "signals", "strategy_run_id",
        existing_type=postgresql.UUID(as_uuid=True), nullable=True,
    )
    op.alter_column(
        "signals", "strategy_version_id",
        existing_type=postgresql.UUID(as_uuid=True), nullable=True,
    )
    op.create_foreign_key(
        "fk_signals_strategy_run_id_strategy_runs", "signals", "strategy_runs",
        ["strategy_run_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_signals_strategy_version_id_strategy_versions", "signals", "strategy_versions",
        ["strategy_version_id"], ["id"], ondelete="SET NULL",
    )

    # 2. Provenance + idempotency identity + state columns.
    op.add_column("signals", sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=False))
    op.add_column("signals", sa.Column("identity_key", sa.String(length=128), nullable=False))
    op.add_column("signals", sa.Column("content_hash", sa.String(length=128), nullable=False))
    op.add_column("signals", sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=False))
    op.add_column("signals", sa.Column("strategy_version", sa.String(length=64), nullable=False))
    op.add_column("signals", sa.Column("config_hash", sa.String(length=128), nullable=False))
    op.add_column("signals", sa.Column("code_hash", sa.String(length=128), nullable=True))
    op.add_column("signals", sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "signals",
        sa.Column("state", sa.String(length=32), nullable=False, server_default=sa.text("'received'")),
    )
    op.add_column("signals", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))

    # 3. Idempotency + identity uniqueness.
    op.create_unique_constraint("uq_signals_signal_id", "signals", ["signal_id"])
    op.create_unique_constraint("uq_signals_identity_key", "signals", ["identity_key"])


def downgrade() -> None:
    op.drop_constraint("uq_signals_identity_key", "signals", type_="unique")
    op.drop_constraint("uq_signals_signal_id", "signals", type_="unique")
    op.drop_column("signals", "processed_at")
    op.drop_column("signals", "state")
    op.drop_column("signals", "run_id")
    op.drop_column("signals", "code_hash")
    op.drop_column("signals", "config_hash")
    op.drop_column("signals", "strategy_version")
    op.drop_column("signals", "strategy_id")
    op.drop_column("signals", "content_hash")
    op.drop_column("signals", "identity_key")
    op.drop_column("signals", "signal_id")

    op.drop_constraint("fk_signals_strategy_version_id_strategy_versions", "signals", type_="foreignkey")
    op.drop_constraint("fk_signals_strategy_run_id_strategy_runs", "signals", type_="foreignkey")
    op.alter_column(
        "signals", "strategy_version_id",
        existing_type=postgresql.UUID(as_uuid=True), nullable=False,
    )
    op.alter_column(
        "signals", "strategy_run_id",
        existing_type=postgresql.UUID(as_uuid=True), nullable=False,
    )
    op.create_foreign_key(
        "fk_signals_strategy_version_id_strategy_versions", "signals", "strategy_versions",
        ["strategy_version_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_signals_strategy_run_id_strategy_runs", "signals", "strategy_runs",
        ["strategy_run_id"], ["id"], ondelete="CASCADE",
    )
