"""Execution adapter boundary (Phase 9) — provider-neutral, no broker SDK.

Defines the `ExecutionAdapter` interface, `ExecutionRequest` (the normalized
OMS-approved order the engine dispatches), `ExecutionResponse` (the provider
outcome), `ExecutionCapabilities`, and a deterministic `InMemoryAdapter`
(TEST_ADAPTER) that must never be mistaken for a real broker.

Phase 10 owns concrete broker adapters; Phase 9 only defines the boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from alpha_algo_execution_engine.errors import FailureClass
from alpha_algo_execution_engine.state import ExecutionSubmissionState


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class ExecutionCapabilities:
    """What an adapter can do — used to gate dispatch safely."""

    provider_name: str = "test"
    supports_live_trading: bool = False
    supports_cancellation: bool = True
    supports_partial_fills: bool = True


@dataclass(frozen=True)
class ExecutionRequest:
    """The normalized, OMS-approved order the engine dispatches to an adapter."""

    order_id: UUID
    client_order_id: str
    execution_id: str
    correlation_id: str | None
    account_id: UUID
    instrument_id: UUID
    signal_id: UUID
    strategy_id: UUID
    strategy_version: str
    side: str
    quantity: int
    order_type: str
    limit_price: Decimal | None
    trading_mode: str
    risk_approval_id: str
    approval_expires_at: datetime
    binding_hash: str
    orchestration_id: str

    def __post_init__(self) -> None:
        _require_timezone(self.approval_expires_at, "approval_expires_at")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if not self.client_order_id.strip():
            raise ValueError("client_order_id is required")
        if not self.execution_id.strip():
            raise ValueError("execution_id is required")


@dataclass(frozen=True)
class ExecutionResponse:
    """A definitive provider outcome (or an ambiguous one the engine classifies)."""

    status: ExecutionSubmissionState
    reason: str
    occurred_at: datetime
    broker_order_id: str | None = None
    failure_class: FailureClass | None = None

    def __post_init__(self) -> None:
        _require_timezone(self.occurred_at, "occurred_at")


class ExecutionAdapter(Protocol):
    """Provider-neutral execution boundary (Phase 10 provides concrete adapters)."""

    capabilities: ExecutionCapabilities

    def submit(self, request: ExecutionRequest) -> ExecutionResponse: ...

    def cancel(self, order_id: UUID) -> ExecutionResponse: ...

    def health(self) -> bool: ...


class InMemoryAdapter:
    """Deterministic TEST_ADAPTER — never a real broker, never LIVE.

    Configurable for tests: a fixed ``response`` for successful submits, an
    optional ``raise_error`` (transient/timeout/unknown) to exercise failure
    paths, and recorded submission/cancel calls.
    """

    def __init__(
        self,
        *,
        response: ExecutionResponse | None = None,
        raise_error: Exception | None = None,
        cancel_response: ExecutionResponse | None = None,
        capabilities: ExecutionCapabilities | None = None,
    ) -> None:
        self._response = response
        self._raise_error = raise_error
        self._cancel_response = cancel_response
        self.capabilities = capabilities or ExecutionCapabilities(
            provider_name="test", supports_live_trading=False
        )
        self.submissions: list[ExecutionRequest] = []
        self.cancellations: list[UUID] = []

    def submit(self, request: ExecutionRequest) -> ExecutionResponse:
        self.submissions.append(request)
        if self._raise_error is not None:
            raise self._raise_error
        if self._response is not None:
            return self._response
        # Default: immediate acknowledgement.
        return ExecutionResponse(
            status=ExecutionSubmissionState.ACKNOWLEDGED,
            reason="acknowledged by test adapter",
            occurred_at=request.approval_expires_at,
            broker_order_id=f"test-broker-{request.order_id}",
        )

    def cancel(self, order_id: UUID) -> ExecutionResponse:
        self.cancellations.append(order_id)
        if self._cancel_response is not None:
            return self._cancel_response
        return ExecutionResponse(
            status=ExecutionSubmissionState.UNKNOWN,
            reason="cancellation accepted; confirmation pending",
            occurred_at=_now(),
        )

    def health(self) -> bool:
        return True


def _now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
