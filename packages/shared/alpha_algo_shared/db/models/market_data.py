from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from alpha_algo_shared.db.base import Base, TimestampMixin


class Tick(TimestampMixin, Base):
    __tablename__ = "ticks"
    __table_args__ = (
        UniqueConstraint("source_broker", "source_sequence", "timestamp", name="uq_ticks_source_broker_sequence_timestamp"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(String(100), nullable=False)
    ltp: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    ask: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    bid_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ask_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_broker: Mapped[str] = mapped_column(String(50), nullable=False)
    source_sequence: Mapped[str | None] = mapped_column(String(150), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Candle(TimestampMixin, Base):
    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("instrument_id", "timeframe", "candle_start", name="uq_candles_instrument_timeframe_start"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    candle_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    timeframe: Mapped[str] = mapped_column(String(20), nullable=False)
    open_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    high_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    low_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    close_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_broker: Mapped[str | None] = mapped_column(String(50), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketDepth(TimestampMixin, Base):
    __tablename__ = "market_depth"
    __table_args__ = (
        UniqueConstraint(
            "source_broker",
            "source_sequence",
            "timestamp",
            name="uq_market_depth_source_broker_sequence_timestamp",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_broker: Mapped[str] = mapped_column(String(50), nullable=False)
    source_sequence: Mapped[str | None] = mapped_column(String(150), nullable=True)
    bid_levels: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    ask_levels: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IndicatorValue(TimestampMixin, Base):
    __tablename__ = "indicator_values"
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "strategy_run_id",
            "indicator_name",
            "timeframe",
            "calculated_at",
            name="uq_indicator_values_scope_name_timeframe_calculated_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True, nullable=False)
    instrument_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("strategy_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    indicator_name: Mapped[str] = mapped_column(String(100), nullable=False)
    timeframe: Mapped[str | None] = mapped_column(String(20), nullable=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    values_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

