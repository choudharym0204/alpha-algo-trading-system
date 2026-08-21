"""Order Management System service (Phase 8).

Transforms a Phase-7 ``TradingIntent`` into a durable internal order, drives the
existing 11-state ``OrderLifecycle`` from INTENT_CREATED to SUBMISSION_REQUESTED,
persists append-only order events, and stops at the explicit execution boundary.

The OMS never dispatches to a broker, never fakes broker acknowledgments/fills,
and never enables LIVE. LIVE / unknown trading modes are blocked fail-closed.

Idempotency contract:
* replay (same orchestration_id + same immutable payload) -> returns the existing
  order with ``duplicate=True`` (no second order).
* conflict (same orchestration_id + different payload) -> raises ``IntentConflictError``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable
from uuid import UUID, uuid4

from alpha_algo_execution_engine.lifecycle import (
    OrderLifecycle,
    OrderState,
)
from alpha_algo_execution_engine.submission import BrokerSubmissionIntent
from alpha_algo_trading_engine.intent import TradingIntent

from alpha_algo_oms.boundary import (
    ExecutionBoundary,
    SubmissionHandoff,
)
from alpha_algo_oms.errors import (
    IntentConflictError,
    InvalidStateTransitionError,
    OrderNotFoundError,
    OrderValidationError,
    PersistenceError,
    RiskApprovalError,
)
from alpha_algo_oms.identity import OrderIdentity, build_order_identity
from alpha_algo_oms.metrics import OmsMetrics
from alpha_algo_oms.repository import (
    OUTCOME_DUPLICATE,
    OrderRepository,
    to_orm_event,
    to_orm_order,
)
from alpha_algo_oms.validation import OrderSpec, validate_intent

logger = logging.getLogger(__name__)

_EVT_ORDER_CREATED = "ORDER_CREATED"
_EVT_INTERNAL_ORDER_CREATED = "INTERNAL_ORDER_CREATED"
_EVT_SUBMISSION_REQUESTED = "SUBMISSION_REQUESTED"
_EVT_CANCEL_REQUESTED = "CANCEL_REQUESTED"


@dataclass(frozen=True)
class OrderResult:
    """The outcome of an OMS order operation."""

    order_id: UUID
    client_order_id: str
    orchestration_id: str
    status: OrderState
    duplicate: bool = False
    created: bool = False
    reason: str = ""


class OmsService:
    def __init__(
        self,
        *,
        repository: OrderRepository | None = None,
        execution_boundary: ExecutionBoundary | None = None,
        metrics: OmsMetrics | None = None,
        clock: Callable[[], datetime] | None = None,
        global_halt_active: Callable[[], bool] | None = None,
    ) -> None:
        self._repository = repository
        self._boundary = execution_boundary or ExecutionBoundary()
        self._metrics = metrics or OmsMetrics()
        self._clock = clock or (lambda: datetime.now(tz=UTC))
        # Fail-closed default: global halt is active unless a provider says otherwise.
        self._global_halt_active = global_halt_active or (lambda: True)

    # ------------------------------------------------------------------ create
    def create_order(self, intent: TradingIntent) -> OrderResult:
        """Create an internal order from an OMS-ready intent.

        Flow: validate -> identity -> idempotency -> transactional create ->
        INTENT_CREATED -> INTERNAL_ORDER_CREATED -> SUBMISSION_REQUESTED ->
        execution boundary. No broker call.
        """
        spec = validate_intent(
            intent,
            now=self._clock(),
            global_halt_active=self._global_halt_active(),
        )

        identity = build_order_identity(
            intent, internal_order_id=uuid4(), quantity=spec.quantity
        )

        if self._repository is None:
            return self._create_in_memory(spec, identity)
        return self._create_with_persistence(spec, identity)

    def _create_with_persistence(
        self, spec: OrderSpec, identity: OrderIdentity
    ) -> OrderResult:
        existing = self._repository.find_by_orchestration_id(spec.orchestration_id)
        if existing is not None:
            return self._resolve_existing(existing, identity)

        order = to_orm_order(spec, identity)
        initial_event = to_orm_event(
            order_id=identity.internal_order_id,
            event_type=_EVT_ORDER_CREATED,
            previous_status=None,
            new_status=OrderState.INTENT_CREATED.value,
            event_timestamp=self._clock(),
            reason="internal order created from validated intent",
            source_event_id=f"create-{spec.orchestration_id}",
        )

        try:
            outcome, order_id = self._repository.create_order(order, initial_event)
        except PersistenceError:
            raise
        except Exception as exc:  # DB failure -> no false success
            self._metrics.record_persistence_failure()
            raise PersistenceError("order creation failed") from exc

        if outcome == OUTCOME_DUPLICATE:
            self._metrics.record_duplicate_order()
            # Race: another worker inserted it first. Resolve idempotently.
            raced = self._repository.find_by_id(order_id)
            return self._resolve_existing(raced, identity)

        self._metrics.record_created()
        return self._advance_to_submission(order_id, identity, spec)

    def _create_in_memory(
        self, spec: OrderSpec, identity: OrderIdentity
    ) -> OrderResult:
        # No repository configured: validate + run the pure lifecycle only.
        self._metrics.record_created()
        lifecycle = OrderLifecycle(order_id=identity.internal_order_id)
        lifecycle = lifecycle.transition_to(
            OrderState.INTERNAL_ORDER_CREATED,
            occurred_at=self._clock(),
            reason="internal order created",
        )
        lifecycle = self._request_submission(lifecycle, spec)
        return OrderResult(
            order_id=identity.internal_order_id,
            client_order_id=identity.client_order_id,
            orchestration_id=spec.orchestration_id,
            status=lifecycle.state,
            created=True,
        )

    def _resolve_existing(self, existing, identity: OrderIdentity) -> OrderResult:
        if existing is None:
            raise OrderValidationError("order not found during duplicate resolution")
        if existing.order_identity_key == identity.order_identity_key:
            self._metrics.record_duplicate_intent()
            return OrderResult(
                order_id=existing.id,
                client_order_id=existing.client_order_id,
                orchestration_id=existing.orchestration_id or "",
                status=OrderState(existing.status),
                duplicate=True,
            )
        self._metrics.record_conflict()
        raise IntentConflictError(
            "same orchestration_id with a different immutable payload"
        )

    def _advance_to_submission(
        self, order_id: UUID, identity: OrderIdentity, spec: OrderSpec
    ) -> OrderResult:
        now = self._clock()
        lifecycle = OrderLifecycle(order_id=order_id)

        # INTENT_CREATED -> INTERNAL_ORDER_CREATED
        lifecycle = lifecycle.transition_to(
            OrderState.INTERNAL_ORDER_CREATED,
            occurred_at=now,
            reason="internal order identity established",
        )
        self._append_transition(
            order_id,
            event_type=_EVT_INTERNAL_ORDER_CREATED,
            previous=OrderState.INTENT_CREATED,
            new=OrderState.INTERNAL_ORDER_CREATED,
            reason="internal order created",
            source_event_id=f"{spec.orchestration_id}-internal",
            timestamp=now,
        )

        # INTERNAL_ORDER_CREATED -> SUBMISSION_REQUESTED
        lifecycle = self._request_submission(lifecycle, spec)
        self._append_transition(
            order_id,
            event_type=_EVT_SUBMISSION_REQUESTED,
            previous=OrderState.INTERNAL_ORDER_CREATED,
            new=OrderState.SUBMISSION_REQUESTED,
            reason="risk approval re-validated; submission requested",
            source_event_id=f"{spec.orchestration_id}-submission",
            timestamp=self._clock(),
        )

        handoff = SubmissionHandoff(
            order_id=order_id,
            broker_submission_intent=BrokerSubmissionIntent(
                order_id=order_id,
                signal_id=spec.signal_id,
                strategy_id=spec.strategy_id,
                instrument_id=spec.instrument_id,
                risk_approval_id=UUID(spec.risk_approval_id),
                requested_at=self._clock(),
                metadata={"orchestration_id": spec.orchestration_id},
            ),
        )
        self._boundary.submit(handoff)

        return OrderResult(
            order_id=order_id,
            client_order_id=identity.client_order_id,
            orchestration_id=spec.orchestration_id,
            status=lifecycle.state,
            created=True,
        )

    def _append_transition(
        self,
        order_id: UUID,
        *,
        event_type: str,
        previous: OrderState,
        new: OrderState,
        reason: str,
        source_event_id: str,
        timestamp: datetime,
    ) -> None:
        event = to_orm_event(
            order_id=order_id,
            event_type=event_type,
            previous_status=previous.value,
            new_status=new.value,
            event_timestamp=timestamp,
            reason=reason,
            source_event_id=source_event_id,
        )
        try:
            self._repository.append_event(order_id, event, new_status=new.value)
        except Exception as exc:
            self._metrics.record_persistence_failure()
            raise PersistenceError(f"failed to persist {event_type}") from exc
        self._metrics.record_transition()

    def _request_submission(
        self, lifecycle: OrderLifecycle, spec: OrderSpec
    ) -> OrderLifecycle:
        """Re-validate approval binding then transition to SUBMISSION_REQUESTED."""
        if spec.approval_expires_at <= self._clock():
            self._metrics.record_rejection()
            raise RiskApprovalError("risk approval is expired")
        if not spec.risk_approval_id or not spec.risk_approval_id.strip():
            raise RiskApprovalError("risk approval id is missing")
        try:
            return lifecycle.transition_to(
                OrderState.SUBMISSION_REQUESTED,
                occurred_at=self._clock(),
                reason="risk approval re-validated; submission requested",
                metadata={"risk_approval_id": spec.risk_approval_id},
            )
        except Exception as exc:
            raise InvalidStateTransitionError(str(exc)) from exc

    # ------------------------------------------------------------- cancellation
    def request_cancellation(self, order_id: UUID) -> OrderResult:
        """Request internal cancellation (CANCEL_REQUESTED; never reports CANCELLED)."""
        if self._repository is None:
            raise OrderNotFoundError("no repository configured")
        order = self._repository.find_by_id(order_id)
        if order is None:
            raise OrderNotFoundError("order not found")
        current = OrderState(order.status)
        if current not in {
            OrderState.SUBMISSION_REQUESTED,
            OrderState.BROKER_ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
        }:
            raise InvalidStateTransitionError(
                f"cannot request cancellation from {current.value}"
            )
        now = self._clock()
        event = to_orm_event(
            order_id=order_id,
            event_type=_EVT_CANCEL_REQUESTED,
            previous_status=current.value,
            new_status=OrderState.CANCEL_REQUESTED.value,
            event_timestamp=now,
            reason="cancellation requested",
            source_event_id=f"{order.order_identity_key or order_id}-cancel",
        )
        try:
            self._repository.append_event(
                order_id, event, new_status=OrderState.CANCEL_REQUESTED.value
            )
        except Exception as exc:
            self._metrics.record_persistence_failure()
            raise PersistenceError("failed to persist cancellation") from exc
        self._metrics.record_cancellation_request()
        return OrderResult(
            order_id=order_id,
            client_order_id=order.client_order_id,
            orchestration_id=order.orchestration_id or "",
            status=OrderState.CANCEL_REQUESTED,
            reason="cancellation requested",
        )

    # ------------------------------------------------------------------- reads
    def get_order(self, order_id: UUID) -> OrderResult | None:
        if self._repository is None:
            return None
        order = self._repository.find_by_id(order_id)
        if order is None:
            return None
        return OrderResult(
            order_id=order.id,
            client_order_id=order.client_order_id,
            orchestration_id=order.orchestration_id or "",
            status=OrderState(order.status),
        )

    def list_orders(self, *, limit: int = 100):
        if self._repository is None:
            return []
        return self._repository.list_orders(limit=limit)

    def get_order_events(self, order_id: UUID):
        if self._repository is None:
            return []
        return self._repository.get_events(order_id)
