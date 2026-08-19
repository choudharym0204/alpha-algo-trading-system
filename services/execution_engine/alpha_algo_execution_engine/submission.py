from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from alpha_algo_contracts import RiskDecision, RiskDecisionResult
from alpha_algo_execution_engine.lifecycle import OrderLifecycle, OrderState


class RiskApprovalRequired(ValueError):
    pass


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class BrokerSubmissionIntent:
    order_id: UUID
    signal_id: UUID
    strategy_id: UUID
    instrument_id: UUID
    risk_approval_id: UUID
    requested_at: datetime
    metadata: dict[str, object]

    def __post_init__(self) -> None:
        _require_timezone(self.requested_at, "requested_at")


@dataclass(frozen=True)
class BrokerSubmissionGuard:
    def request_submission(
        self,
        *,
        lifecycle: OrderLifecycle,
        risk_decision: RiskDecision | None,
        signal_id: UUID,
        strategy_id: UUID,
        instrument_id: UUID,
        requested_at: datetime,
        metadata: dict[str, object] | None = None,
    ) -> tuple[OrderLifecycle, BrokerSubmissionIntent]:
        _require_timezone(requested_at, "requested_at")
        self._validate_risk_decision(
            risk_decision=risk_decision,
            signal_id=signal_id,
            strategy_id=strategy_id,
            instrument_id=instrument_id,
            requested_at=requested_at,
        )

        assert risk_decision is not None
        assert risk_decision.approval_id is not None

        next_lifecycle = lifecycle.transition_to(
            OrderState.SUBMISSION_REQUESTED,
            occurred_at=requested_at,
            reason="valid risk approval accepted for broker submission request",
            metadata={
                "risk_decision_id": str(risk_decision.decision_id),
                "risk_approval_id": str(risk_decision.approval_id),
                **(metadata or {}),
            },
        )

        intent = BrokerSubmissionIntent(
            order_id=lifecycle.order_id,
            signal_id=signal_id,
            strategy_id=strategy_id,
            instrument_id=instrument_id,
            risk_approval_id=risk_decision.approval_id,
            requested_at=requested_at,
            metadata={
                "risk_decision_id": str(risk_decision.decision_id),
                **(metadata or {}),
            },
        )
        return next_lifecycle, intent

    def _validate_risk_decision(
        self,
        *,
        risk_decision: RiskDecision | None,
        signal_id: UUID,
        strategy_id: UUID,
        instrument_id: UUID,
        requested_at: datetime,
    ) -> None:
        if risk_decision is None:
            raise RiskApprovalRequired("risk approval is required before broker submission")
        if risk_decision.decision != RiskDecisionResult.APPROVED:
            raise RiskApprovalRequired("risk decision is not approved")
        if not risk_decision.is_valid_approval_at(requested_at):
            raise RiskApprovalRequired("risk approval is expired or invalid")
        if risk_decision.signal_id != signal_id:
            raise RiskApprovalRequired("risk approval signal_id does not match order intent")
        if risk_decision.strategy_id != strategy_id:
            raise RiskApprovalRequired("risk approval strategy_id does not match order intent")
        if risk_decision.instrument_id != instrument_id:
            raise RiskApprovalRequired("risk approval instrument_id does not match order intent")
