from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CandleTimeframe(StrEnum):
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"


class MarketTick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: UUID
    exchange: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=100)
    timestamp: datetime
    ltp: Decimal = Field(gt=Decimal("0"))
    volume: int | None = Field(default=None, ge=0)
    bid: Decimal | None = Field(default=None, gt=Decimal("0"))
    ask: Decimal | None = Field(default=None, gt=Decimal("0"))
    bid_quantity: int | None = Field(default=None, ge=0)
    ask_quantity: int | None = Field(default=None, ge=0)
    source_broker: str = Field(min_length=1, max_length=50)
    source_sequence: str = Field(min_length=1, max_length=150)
    received_at: datetime

    @field_validator("timestamp", "received_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("timestamp values must be timezone-aware")
        return value


class MarketCandle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instrument_id: UUID
    exchange: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=100)
    timeframe: CandleTimeframe
    candle_start: datetime
    open_price: Decimal = Field(gt=Decimal("0"))
    high_price: Decimal = Field(gt=Decimal("0"))
    low_price: Decimal = Field(gt=Decimal("0"))
    close_price: Decimal = Field(gt=Decimal("0"))
    volume: int | None = Field(default=None, ge=0)
    source_broker: str = Field(min_length=1, max_length=50)
    generated_at: datetime

    @field_validator("candle_start", "generated_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("timestamp values must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_price_range(self) -> MarketCandle:
        if self.low_price > self.high_price:
            raise ValueError("low_price cannot exceed high_price")
        if not self.low_price <= self.open_price <= self.high_price:
            raise ValueError("open_price must be within candle range")
        if not self.low_price <= self.close_price <= self.high_price:
            raise ValueError("close_price must be within candle range")
        return self

