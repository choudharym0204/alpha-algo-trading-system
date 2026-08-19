"""TimescaleDB tick, candle, market depth, and indicator schema

Revision ID: 20260812_timescale_market_data
Revises: 20260812_safety_audit_events
Create Date: 2026-08-12 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260812_timescale_market_data"
down_revision = "20260812_safety_audit_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "ticks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column(
            "instrument_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=100), nullable=False),
        sa.Column("ltp", sa.Numeric(18, 4), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("bid", sa.Numeric(18, 4), nullable=True),
        sa.Column("ask", sa.Numeric(18, 4), nullable=True),
        sa.Column("bid_quantity", sa.Integer(), nullable=True),
        sa.Column("ask_quantity", sa.Integer(), nullable=True),
        sa.Column("source_broker", sa.String(length=50), nullable=False),
        sa.Column("source_sequence", sa.String(length=150), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("source_broker", "source_sequence", "timestamp", name="uq_ticks_source_broker_sequence_timestamp"),
    )

    op.create_table(
        "candles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("candle_start", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column(
            "instrument_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("timeframe", sa.String(length=20), nullable=False),
        sa.Column("open_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("high_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("low_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("close_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("source_broker", sa.String(length=50), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("instrument_id", "timeframe", "candle_start", name="uq_candles_instrument_timeframe_start"),
    )

    op.create_table(
        "market_depth",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column(
            "instrument_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_broker", sa.String(length=50), nullable=False),
        sa.Column("source_sequence", sa.String(length=150), nullable=True),
        sa.Column("bid_levels", sa.JSON(), nullable=False),
        sa.Column("ask_levels", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "source_broker",
            "source_sequence",
            "timestamp",
            name="uq_market_depth_source_broker_sequence_timestamp",
        ),
    )

    op.create_table(
        "indicator_values",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), primary_key=True, nullable=False),
        sa.Column(
            "instrument_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "strategy_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategy_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("indicator_name", sa.String(length=100), nullable=False),
        sa.Column("timeframe", sa.String(length=20), nullable=True),
        sa.Column("value", sa.Numeric(18, 6), nullable=True),
        sa.Column("values_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "instrument_id",
            "strategy_run_id",
            "indicator_name",
            "timeframe",
            "calculated_at",
            name="uq_indicator_values_scope_name_timeframe_calculated_at",
        ),
    )

    op.execute("SELECT create_hypertable('ticks', 'timestamp', if_not_exists => TRUE)")
    op.execute("SELECT create_hypertable('candles', 'candle_start', if_not_exists => TRUE)")
    op.execute("SELECT create_hypertable('market_depth', 'timestamp', if_not_exists => TRUE)")
    op.execute("SELECT create_hypertable('indicator_values', 'calculated_at', if_not_exists => TRUE)")


def downgrade() -> None:
    op.drop_table("indicator_values")
    op.drop_table("market_depth")
    op.drop_table("candles")
    op.drop_table("ticks")

