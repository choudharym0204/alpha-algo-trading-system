from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from alpha_algo_contracts.signals import StrategySignal


class RiskDecisionResult(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


def _is_timezone_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


class RiskAssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID = Field(default_factory=uuid4)
    signal: StrategySignal
    requested_at: datetime
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("requested_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if not _is_timezone_aware(value):
            raise ValueError("requested_at must be timezone-aware")
        return value


class RiskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    signal_id: UUID
    strategy_id: UUID
    instrument_id: UUID
    decision: RiskDecisionResult
    reason_code: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)
    rule_id: str = Field(min_length=1, max_length=100)
    evaluated_at: datetime
    approval_id: UUID | None = None
    expires_at: datetime | None = None
    binding_hash: str | None = None
    snapshot_id: UUID | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("reason_code", "reason", "rule_id")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be blank")
        return value

    @field_validator("evaluated_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and not _is_timezone_aware(value):
            raise ValueError("timestamp values must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_approval_state(self) -> RiskDecision:
        if self.decision == RiskDecisionResult.APPROVED:
            if self.approval_id is None:
                raise ValueError("approved risk decisions require approval_id")
            if self.expires_at is None:
                raise ValueError("approved risk decisions require expires_at")
            if self.expires_at <= self.evaluated_at:
                raise ValueError("expires_at must be after evaluated_at")
        else:
            if self.approval_id is not None or self.expires_at is not None:
                raise ValueError("rejected risk decisions cannot carry approval fields")
        return self

    def is_valid_approval_at(self, value: datetime) -> bool:
        if not _is_timezone_aware(value):
            raise ValueError("value must be timezone-aware")
        return (
            self.decision == RiskDecisionResult.APPROVED
            and self.approval_id is not None
            and self.expires_at is not None
            and value < self.expires_at
        )
