"""Execution Engine (Phase 9).

Consumes the OMS Execution Port, validates + dispatches the OMS-approved order
to a provider-neutral `ExecutionAdapter`, and manages the execution lifecycle:
submission state, bounded classification-based retry, timeout→UNKNOWN semantics,
cancellation, event normalization/deduplication, and OMS lifecycle updates
through trusted events only.

The engine never contains broker-specific logic, never fakes broker acks/fills,
and never enables LIVE. Phase 10 owns concrete broker adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Protocol
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from alpha_algo_execution_engine.adapter import (
    ExecutionAdapter,
    ExecutionRequest,
    ExecutionResponse,
)
from alpha_algo_execution_engine.errors import (
    ExecutionError,
    ExecutionTimeoutError,
    ExecutionTransientError,
    ExecutionValidationError,
    FailureClass,
)
from alpha_algo_execution_engine.events import (
    BrokerOrderEvent,
    OrderEventType,
    OrderExecutionState,
)
from alpha_algo_execution_engine.identity import (
    compute_attempt_id,
    compute_event_identity,
    event_content_hash,
)
from alpha_algo_execution_engine.lifecycle import OrderState
from alpha_algo_execution_engine.metrics import ExecutionMetrics
from alpha_algo_execution_engine.state import (
    ExecutionAttempt,
    ExecutionSubmissionState,
)

_ALLOWED_MODES = frozenset({"BACKTEST", "PAPER"})


@dataclass(frozen=True)
class ExecutionOutcome:
    """The result of an execution operation (submit / cancel / apply_event)."""

    order_id: UUID
    execution_id: str
    attempt_id: str
    submission_state: ExecutionSubmissionState
    order_state: OrderState | None
    broker_order_id: str | None
    reason: str
    duplicate: bool = False


class ExecutionRepository(Protocol):
    """Durable execution state the engine relies on (attempts + events + orders)."""

    def find_attempt(
        self, execution_id: str, attempt_number: int
    ) -> ExecutionAttempt | None: ...

    def save_attempt(self, attempt: ExecutionAttempt) -> None: ...

    def update_attempt(
        self,
        attempt_id: str,
        *,
        state: ExecutionSubmissionState,
        broker_order_id: str | None = None,
        responded_at: datetime | None = None,
        reason: str | None = None,
    ) -> None: ...

    def has_event(self, order_id: UUID, event_identity: str) -> bool: ...

    def get_event_hash(self, order_id: UUID, event_identity: str) -> str | None: ...

    def save_event(
        self,
        order_id: UUID,
        event: BrokerOrderEvent,
        new_state: OrderExecutionState,
        event_identity: str,
    ) -> None: ...

    def load_execution_state(self, order_id: UUID) -> OrderExecutionState | None: ...


class ExecutionEngine:
    def __init__(
        self,
        *,
        adapter: ExecutionAdapter,
        repository: ExecutionRepository | None = None,
        metrics: ExecutionMetrics | None = None,
        clock: Callable[[], datetime] | None = None,
        max_retries: int = 0,
        global_halt_active: Callable[[], bool] | None = None,
    ) -> None:
        self._adapter = adapter
        self._repository = repository
        self._metrics = metrics or ExecutionMetrics()
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        self._max_retries = max_retries
        self._global_halt_active = global_halt_active or (lambda: True)

    # ------------------------------------------------------------------ submit
    def submit(self, request: ExecutionRequest) -> ExecutionOutcome:
        self._metrics.record_request()
        self._validate_request(request)

        existing = self._find_existing(request)
        if existing is not None:
            self._metrics.record_duplicate_request()
            return self._outcome(existing, request, duplicate=True)

        attempt_number = 0
        attempt = self._new_attempt(request, attempt_number)
        while True:
            try:
                self._persist(attempt)
            except IntegrityError:
                # Concurrent duplicate attempt — re-read the winner.
                existing = self._find_existing(request)
                if existing is not None:
                    self._metrics.record_duplicate_request()
                    return self._outcome(existing, request, duplicate=True)
                raise
            try:
                self._metrics.record_submission()
                response = self._adapter.submit(request)
            except ExecutionTransientError as exc:
                if attempt_number < self._max_retries:
                    attempt_number += 1
                    self._metrics.record_retry()
                    attempt = self._new_attempt(request, attempt_number)
                    continue
                self._metrics.record_failure()
                return self._finalize(
                    attempt, ExecutionSubmissionState.REJECTED, None, str(exc), request
                )
            except ExecutionTimeoutError as exc:
                self._metrics.record_timeout()
                return self._finalize_timeout(attempt, str(exc), request)
            except ExecutionError as exc:
                self._metrics.record_failure()
                if exc.failure_class == FailureClass.UNKNOWN_EXTERNAL_STATE:
                    return self._finalize(
                        attempt,
                        ExecutionSubmissionState.UNKNOWN,
                        None,
                        str(exc),
                        request,
                    )
                return self._finalize(
                    attempt,
                    ExecutionSubmissionState.REJECTED,
                    None,
                    str(exc),
                    request,
                )
            return self._process_response(attempt, response, request)

    def _validate_request(self, request: ExecutionRequest) -> None:
        mode = (request.trading_mode or "").upper()
        if mode == "LIVE":
            self._metrics.record_validation_rejection()
            raise ExecutionValidationError("LIVE trading is disabled (fail-closed)")
        if mode not in _ALLOWED_MODES:
            self._metrics.record_validation_rejection()
            raise ExecutionValidationError(
                f"unknown trading mode: {request.trading_mode}"
            )
        if self._global_halt_active():
            self._metrics.record_validation_rejection()
            raise ExecutionValidationError(
                "global trading halt is active; submission refused"
            )
        if request.approval_expires_at <= self._clock():
            self._metrics.record_validation_rejection()
            raise ExecutionValidationError("risk approval is expired")
        if not request.risk_approval_id or not request.risk_approval_id.strip():
            self._metrics.record_validation_rejection()
            raise ExecutionValidationError("risk approval id is missing")

    def _find_existing(
        self, request: ExecutionRequest
    ) -> ExecutionAttempt | None:
        if self._repository is None:
            return None
        return self._repository.find_attempt(request.execution_id, 0)

    def _new_attempt(
        self, request: ExecutionRequest, attempt_number: int
    ) -> ExecutionAttempt:
        return ExecutionAttempt(
            attempt_id=compute_attempt_id(request.execution_id, attempt_number),
            execution_id=request.execution_id,
            order_id=request.order_id,
            attempt_number=attempt_number,
            state=ExecutionSubmissionState.SUBMISSION_IN_PROGRESS,
            submitted_at=self._clock(),
        )

    def _persist(self, attempt: ExecutionAttempt) -> None:
        if self._repository is not None:
            self._repository.save_attempt(attempt)

    def _process_response(
        self, attempt: ExecutionAttempt, response: ExecutionResponse, request
    ) -> ExecutionOutcome:
        status = response.status
        if status == ExecutionSubmissionState.ACKNOWLEDGED:
            self._metrics.record_acknowledgment()
            self._apply_order_event(
                BrokerOrderEvent(
                    order_id=request.order_id,
                    event_type=OrderEventType.BROKER_ACKNOWLEDGED,
                    occurred_at=response.occurred_at,
                    reason=response.reason,
                    broker_order_id=response.broker_order_id,
                )
            )
            return self._finalize(
                attempt,
                ExecutionSubmissionState.ACKNOWLEDGED,
                response.broker_order_id,
                response.reason,
                request,
                order_state=OrderState.BROKER_ACKNOWLEDGED,
            )
        if status == ExecutionSubmissionState.SUBMITTED:
            return self._finalize(
                attempt,
                ExecutionSubmissionState.SUBMITTED,
                response.broker_order_id,
                response.reason,
                request,
                order_state=OrderState.SUBMISSION_REQUESTED,
            )
        if status == ExecutionSubmissionState.REJECTED:
            self._metrics.record_reject()
            self._apply_order_event(
                BrokerOrderEvent(
                    order_id=request.order_id,
                    event_type=OrderEventType.REJECTED,
                    occurred_at=response.occurred_at,
                    reason=response.reason,
                    broker_order_id=response.broker_order_id,
                )
            )
            return self._finalize(
                attempt,
                ExecutionSubmissionState.REJECTED,
                response.broker_order_id,
                response.reason,
                request,
                order_state=OrderState.REJECTED,
            )
        if status in (ExecutionSubmissionState.TIMEOUT, ExecutionSubmissionState.UNKNOWN):
            self._metrics.record_unknown()
            self._apply_order_event(
                BrokerOrderEvent(
                    order_id=request.order_id,
                    event_type=OrderEventType.UNKNOWN,
                    occurred_at=response.occurred_at,
                    reason=response.reason,
                    broker_order_id=response.broker_order_id,
                )
            )
            return self._finalize(
                attempt,
                status,
                response.broker_order_id,
                response.reason,
                request,
                order_state=OrderState.UNKNOWN,
            )
        self._metrics.record_failure()
        return self._finalize(
            attempt,
            ExecutionSubmissionState.UNKNOWN,
            response.broker_order_id,
            response.reason,
            request,
            order_state=OrderState.UNKNOWN,
        )

    def _finalize_timeout(
        self, attempt: ExecutionAttempt, reason: str, request: ExecutionRequest
    ) -> ExecutionOutcome:
        self._metrics.record_unknown()
        self._apply_order_event(
            BrokerOrderEvent(
                order_id=request.order_id,
                event_type=OrderEventType.UNKNOWN,
                occurred_at=self._clock(),
                reason=reason,
            )
        )
        return self._finalize(
            attempt,
            ExecutionSubmissionState.TIMEOUT,
            None,
            reason,
            request,
            order_state=OrderState.UNKNOWN,
        )

    def _finalize(
        self,
        attempt: ExecutionAttempt,
        state: ExecutionSubmissionState,
        broker_order_id: str | None,
        reason: str,
        request: ExecutionRequest,
        *,
        order_state: OrderState | None = None,
    ) -> ExecutionOutcome:
        if self._repository is not None:
            self._repository.update_attempt(
                attempt.attempt_id,
                state=state,
                broker_order_id=broker_order_id,
                responded_at=self._clock(),
                reason=reason,
            )
        return ExecutionOutcome(
            order_id=request.order_id,
            execution_id=request.execution_id,
            attempt_id=attempt.attempt_id,
            submission_state=state,
            order_state=order_state,
            broker_order_id=broker_order_id,
            reason=reason,
        )

    def _outcome(
        self, attempt: ExecutionAttempt, request: ExecutionRequest, *, duplicate: bool
    ) -> ExecutionOutcome:
        return ExecutionOutcome(
            order_id=request.order_id,
            execution_id=request.execution_id,
            attempt_id=attempt.attempt_id,
            submission_state=attempt.state,
            order_state=None,
            broker_order_id=attempt.broker_order_id,
            reason=attempt.reason,
            duplicate=duplicate,
        )

    # ------------------------------------------------------------- cancellation
    def cancel(self, order_id: UUID) -> ExecutionOutcome:
        if not self._adapter.capabilities.supports_cancellation:
            return ExecutionOutcome(
                order_id=order_id,
                execution_id="",
                attempt_id="",
                submission_state=ExecutionSubmissionState.REJECTED,
                order_state=None,
                broker_order_id=None,
                reason="cancellation not supported by adapter",
            )
        self._metrics.record_cancellation()
        response = self._adapter.cancel(order_id)
        if response.status == ExecutionSubmissionState.CANCELLED:
            # Authoritative cancellation confirmation.
            self._apply_order_event(
                BrokerOrderEvent(
                    order_id=order_id,
                    event_type=OrderEventType.CANCELLED,
                    occurred_at=response.occurred_at,
                    reason=response.reason,
                    broker_order_id=response.broker_order_id,
                )
            )
            order_state = OrderState.CANCELLED
        elif response.status == ExecutionSubmissionState.REJECTED:
            order_state = OrderState.CANCEL_REQUESTED  # cancellation rejected; stays
        else:
            # TIMEOUT / UNKNOWN -> ambiguous; do NOT claim CANCELLED.
            self._metrics.record_unknown()
            order_state = OrderState.UNKNOWN
        return ExecutionOutcome(
            order_id=order_id,
            execution_id="",
            attempt_id="",
            submission_state=response.status,
            order_state=order_state,
            broker_order_id=response.broker_order_id,
            reason=response.reason,
        )

    # ------------------------------------------------------------------ events
    def apply_event(self, event: BrokerOrderEvent) -> OrderExecutionState:
        if self._repository is None:
            raise ExecutionValidationError("no execution repository configured")

        identity = compute_event_identity(event)
        if self._repository.has_event(event.order_id, identity):
            stored_hash = self._repository.get_event_hash(event.order_id, identity)
            if stored_hash is not None and stored_hash != event_content_hash(event):
                raise ExecutionValidationError(
                    "event identity conflict: same identity, different payload"
                )
            self._metrics.record_duplicate_event()
            state = self._repository.load_execution_state(event.order_id)
            if state is None:
                raise ExecutionValidationError(
                    f"order not found: {event.order_id}"
                )
            return state

        state = self._repository.load_execution_state(event.order_id)
        if state is None:
            raise ExecutionValidationError(f"order not found: {event.order_id}")
        next_state = state.apply_event(event)

        if event.event_type in (OrderEventType.PARTIAL_FILL, OrderEventType.FILL):
            if event.event_type == OrderEventType.PARTIAL_FILL:
                self._metrics.record_partial_fill()
            else:
                self._metrics.record_fill()

        self._repository.save_event(
            event.order_id, event, next_state, identity
        )
        return next_state

    def _apply_order_event(self, event: BrokerOrderEvent) -> None:
        try:
            self.apply_event(event)
        except Exception:  # noqa: BLE001 — order-state update must not crash submit
            return
