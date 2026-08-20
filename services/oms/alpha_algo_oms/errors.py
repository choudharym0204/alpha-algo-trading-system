"""Structured, non-leaky OMS errors (Phase 8).

Every failure mode maps to a distinct, catchable error type so callers can
distinguish validation failures, duplicate requests, conflicts, persistence
failures, and state-transition failures. No stack traces, DB internals,
credentials, or broker secrets are ever exposed through these errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class OmsError(Exception):
    """Base class for all OMS errors."""

    code = "OMS_ERROR"


class OrderValidationError(OmsError):
    """The intent/order representation failed a validation rule."""

    code = "ORDER_VALIDATION_ERROR"


class OrderNotFoundError(OmsError):
    """No order exists for the requested identity."""

    code = "ORDER_NOT_FOUND"


class DuplicateOrderError(OmsError):
    """A semantically identical order already exists (idempotent replay)."""

    code = "DUPLICATE_ORDER"

    def __init__(self, order_id: UUID) -> None:
        super().__init__(f"duplicate order; existing order id={order_id}")
        self.order_id = order_id


class IntentConflictError(OmsError):
    """Same orchestration identity but a different immutable payload."""

    code = "INTENT_CONFLICT"


class RiskApprovalError(OmsError):
    """Risk approval is missing, expired, or does not bind to the intent."""

    code = "RISK_APPROVAL_ERROR"


class TradingModeError(OmsError):
    """Trading mode is LIVE or unknown (fail-closed)."""

    code = "TRADING_MODE_ERROR"


class InvalidStateTransitionError(OmsError):
    """The requested order lifecycle transition is illegal."""

    code = "INVALID_STATE_TRANSITION"


class PersistenceError(OmsError):
    """A database/persistence failure occurred (transaction not committed)."""

    code = "PERSISTENCE_ERROR"


class ExecutionBoundaryError(OmsError):
    """The OMS was asked to act beyond its execution boundary."""

    code = "EXECUTION_BOUNDARY_ERROR"


@dataclass(frozen=True)
class ErrorDetail:
    """Serializable, safe error envelope for API/observability boundaries."""

    code: str
    message: str
    order_id: UUID | None = None
    orchestration_id: str | None = None


def to_error_detail(exc: OmsError) -> ErrorDetail:
    """Convert an OMS error to a safe detail object (no internals leaked)."""
    order_id = getattr(exc, "order_id", None)
    return ErrorDetail(
        code=exc.code,
        message=str(exc),
        order_id=order_id if isinstance(order_id, UUID) else None,
        orchestration_id=getattr(exc, "orchestration_id", None),
    )
