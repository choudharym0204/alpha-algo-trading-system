"""OMS: extend orders with Phase-8 identity/idempotency/provenance columns

Revision ID: 20260819_oms
Revises: 20260819_trading_orchestrator
Create Date: 2026-08-19 00:00:00.000000

Adds the Phase-8 OMS columns to the existing ``orders`` table:

* ``orchestration_id`` (unique) - durable intent-consumption idempotency key
* ``order_identity_key`` (unique) - deterministic order identity (conflict detection)
* ``correlation_id`` - cross-boundary traceability
* ``strategy_id`` / ``strategy_version`` - strategy provenance
* ``risk_approval_id`` (unique) - risk-approval binding (no approval reuse)
* ``approval_expires_at`` - approval expiry for binding re-validation

The base ``orders`` columns were created in ``20260812_trading_domain``; this
migration only adds the Phase-8 delta (no duplicate columns/indexes).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260819_oms"
down_revision = "20260819_trading_orchestrator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("orchestration_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("order_identity_key", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("correlation_id", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("strategy_version", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("risk_approval_id", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_unique_constraint(
        "uq_orders_orchestration_id", "orders", ["orchestration_id"]
    )
    op.create_unique_constraint(
        "uq_orders_order_identity_key", "orders", ["order_identity_key"]
    )
    op.create_unique_constraint(
        "uq_orders_risk_approval_id", "orders", ["risk_approval_id"]
    )
    op.create_index("ix_orders_orchestration_id", "orders", ["orchestration_id"])
    op.create_index("ix_orders_strategy_id", "orders", ["strategy_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_strategy_id", table_name="orders")
    op.drop_index("ix_orders_orchestration_id", table_name="orders")
    op.drop_constraint("uq_orders_risk_approval_id", "orders", type_="unique")
    op.drop_constraint("uq_orders_order_identity_key", "orders", type_="unique")
    op.drop_constraint("uq_orders_orchestration_id", "orders", type_="unique")
    op.drop_column("orders", "approval_expires_at")
    op.drop_column("orders", "risk_approval_id")
    op.drop_column("orders", "strategy_version")
    op.drop_column("orders", "strategy_id")
    op.drop_column("orders", "correlation_id")
    op.drop_column("orders", "order_identity_key")
    op.drop_column("orders", "orchestration_id")
