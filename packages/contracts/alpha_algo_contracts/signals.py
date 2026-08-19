from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SignalAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    EXIT = "EXIT"
    HOLD = "HOLD"


class StrategyVersion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy_id: UUID
    version: str = Field(min_length=1, max_length=64)
    config_hash: str = Field(min_length=1, max_length=128)
    code_hash: str | None = Field(default=None, min_length=1, max_length=128)
    created_at: datetime
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("version", "config_hash", "code_hash")
    @classmethod
    def require_non_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("value cannot be blank")
        return value

    @field_validator("created_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("created_at must be timezone-aware")
        return value


class StrategySignal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: UUID = Field(default_factory=uuid4)
    strategy_id: UUID
    strategy_version: str = Field(min_length=1, max_length=64)
    strategy_config_hash: str = Field(min_length=1, max_length=128)
    instrument_id: UUID
    action: SignalAction
    timestamp: datetime
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    reason: str = Field(min_length=1, max_length=500)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("strategy_version", "strategy_config_hash", "reason")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("timestamp must be timezone-aware")
        return value

    @property
    def audit_key(self) -> str:
        return f"{self.strategy_id}:{self.strategy_version}:{self.strategy_config_hash}:{self.signal_id}"
