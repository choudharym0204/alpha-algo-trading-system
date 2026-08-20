from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from alpha_algo_shared.db.base import Base, TimestampMixin


class Strategy(TimestampMixin, Base):
    __tablename__ = "strategies"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class StrategyVersion(TimestampMixin, Base):
    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version_label", name="uq_strategy_versions_strategy_id_version_label"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_label: Mapped[str] = mapped_column(String(50), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    definition_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))


class StrategyConfig(TimestampMixin, Base):
    __tablename__ = "strategy_configs"
    __table_args__ = (
        UniqueConstraint(
            "strategy_version_id",
            "config_name",
            name="uq_strategy_configs_strategy_version_id_config_name",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    config_name: Mapped[str] = mapped_column(String(100), nullable=False)
    config_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    config_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class StrategyRun(TimestampMixin, Base):
    __tablename__ = "strategy_runs"
    __table_args__ = (
        UniqueConstraint("strategy_version_id", "run_label", name="uq_strategy_runs_strategy_version_id_run_label"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_config_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    trading_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    run_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'created'"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Signal(TimestampMixin, Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("signal_id", name="uq_signals_signal_id"),
        UniqueConstraint("identity_key", name="uq_signals_identity_key"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # Phase-5 provenance + idempotency identity
    signal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    identity_key: Mapped[str] = mapped_column(String(128), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    code_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    run_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    # Relational links (populated once strategy/version/run persistence lands in a
    # later phase; Phase 5 records the runtime provenance above instead).
    strategy_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    strategy_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    signal_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    signal_metadata: Mapped[dict[str, object] | None] = mapped_column("metadata", JSON, nullable=True)
    # Phase-5 signal state + processing timestamp
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'received'"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("orchestration_id", name="uq_orders_orchestration_id"),
        UniqueConstraint("order_identity_key", name="uq_orders_order_identity_key"),
        UniqueConstraint("risk_approval_id", name="uq_orders_risk_approval_id"),
        Index("ix_orders_strategy_run_id", "strategy_run_id"),
        Index("ix_orders_broker_account_id", "broker_account_id"),
        Index("ix_orders_instrument_id", "instrument_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_signal_id", "signal_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    strategy_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    strategy_config_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    signal_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("signals.id", ondelete="SET NULL"),
        nullable=True,
    )
    risk_event_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("risk_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    broker_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    trading_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    client_order_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # Phase-8 OMS: durable intent consumption + order identity + provenance.
    orchestration_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_identity_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    strategy_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    strategy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    risk_approval_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approval_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    time_in_force: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'created'"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    average_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Trade(TimestampMixin, Base):
    __tablename__ = "trades"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    strategy_version_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    strategy_config_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    signal_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("signals.id", ondelete="SET NULL"),
        nullable=True,
    )
    broker_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    trading_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    broker_trade_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fees: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    fill_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Position(TimestampMixin, Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint(
            "strategy_run_id",
            "instrument_id",
            "trading_mode",
            name="uq_positions_strategy_run_id_instrument_id_trading_mode",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    strategy_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    broker_account_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("broker_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    trading_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    average_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    unrealized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'open'"))


class TradingIntentRecord(TimestampMixin, Base):
    """Durable OMS-ready intent produced by the Phase-7 trading orchestrator.

    One row per orchestration identity (``orchestration_id`` unique). This is the
    handoff boundary artifact consumed by Phase 8 (OMS); it is not an order and
    never reaches a broker.
    """

    __tablename__ = "trading_intents"
    __table_args__ = (
        UniqueConstraint("orchestration_id", name="uq_trading_intents_orchestration_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    orchestration_id: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    signal_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("signals.id", ondelete="SET NULL"),
        nullable=True,
    )
    strategy_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    strategy_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy_config_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    strategy_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    account_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    instrument_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str | None] = mapped_column(String(16), nullable=True)
    order_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    trading_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_decision_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    approval_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    binding_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'received'"))
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent_metadata: Mapped[dict[str, object] | None] = mapped_column("intent_metadata", JSON, nullable=True)
