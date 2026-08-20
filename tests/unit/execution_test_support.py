"""Shared helpers for Phase 9 execution-engine tests (not a test module)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from alpha_algo_execution_engine.engine import ExecutionRepository
from alpha_algo_execution_engine.events import (
    BrokerOrderEvent,
    OrderEventType,
    OrderExecutionState,
)
from alpha_algo_execution_engine.identity import compute_execution_id, event_content_hash
from alpha_algo_execution_engine.lifecycle import OrderLifecycle, OrderState
from alpha_algo_execution_engine.state import (
    ExecutionAttempt,
    ExecutionSubmissionState,
)


class DuplicateAttempt(IntegrityError):
    """Raised by the in-memory store to mimic the attempt unique constraint."""

    def __init__(self, message: str = "duplicate attempt (unique constraint)") -> None:
        super().__init__(message, params=None, orig=RuntimeError(message))


def make_request(
    *,
    order_id: UUID | None = None,
    quantity: int = 100,
    trading_mode: str = "PAPER",
    approval_expires_at: datetime | None = None,
    order_identity_key: str | None = None,
    risk_approval_id: str | None = None,
    **overrides,
):
    from alpha_algo_execution_engine.adapter import ExecutionRequest

    oid = order_id or uuid4()
    ident_key = order_identity_key or ("k" * 64)
    return ExecutionRequest(
        order_id=oid,
        client_order_id=f"ord-{oid}",
        execution_id=compute_execution_id(oid, ident_key),
        correlation_id=str(uuid4()),
        account_id=uuid4(),
        instrument_id=uuid4(),
        signal_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version="1.0.0",
        side="BUY",
        quantity=quantity,
        order_type="MARKET",
        limit_price=None,
        trading_mode=trading_mode,
        risk_approval_id=(
            risk_approval_id if risk_approval_id is not None else str(uuid4())
        ),
        approval_expires_at=approval_expires_at
        or (datetime.now(UTC) + timedelta(seconds=30)),
        binding_hash="b" * 64,
        orchestration_id=f"orch-{oid}",
        **overrides,
    )


def make_submitted_state(order_id: UUID, quantity: int = 100) -> OrderExecutionState:
    lifecycle = (
        OrderLifecycle(order_id=order_id)
        .transition_to(
            OrderState.INTERNAL_ORDER_CREATED,
            occurred_at=datetime.now(UTC),
            reason="internal order created",
        )
        .transition_to(
            OrderState.SUBMISSION_REQUESTED,
            occurred_at=datetime.now(UTC),
            reason="submission requested",
        )
    )
    return OrderExecutionState(lifecycle=lifecycle, order_quantity=Decimal(quantity))


class InMemoryExecutionRepository(ExecutionRepository):
    """In-memory execution state store mirroring the durable semantics."""

    def __init__(self) -> None:
        self.attempts: dict[tuple[str, int], ExecutionAttempt] = {}
        self.events: dict[str, str] = {}  # event_identity -> content_hash
        self.order_states: dict[UUID, OrderExecutionState] = {}
        self.saved_events: list[tuple[UUID, BrokerOrderEvent]] = []

    def register_order(self, order_id: UUID, quantity: int = 100) -> None:
        self.order_states[order_id] = make_submitted_state(order_id, quantity)

    def find_attempt(
        self, execution_id: str, attempt_number: int
    ) -> ExecutionAttempt | None:
        return self.attempts.get((execution_id, attempt_number))

    def save_attempt(self, attempt: ExecutionAttempt) -> None:
        key = (attempt.execution_id, attempt.attempt_number)
        if key in self.attempts:
            raise DuplicateAttempt("duplicate attempt (unique constraint)")
        self.attempts[key] = attempt

    def update_attempt(
        self,
        attempt_id: str,
        *,
        state: ExecutionSubmissionState,
        broker_order_id: str | None = None,
        responded_at: datetime | None = None,
        reason: str | None = None,
    ) -> None:
        execution_id, attempt_number = _split_attempt_id(attempt_id)
        attempt = self.attempts.get((execution_id, attempt_number))
        if attempt is None:
            return
        self.attempts[(execution_id, attempt_number)] = ExecutionAttempt(
            attempt_id=attempt.attempt_id,
            execution_id=attempt.execution_id,
            order_id=attempt.order_id,
            attempt_number=attempt.attempt_number,
            state=state,
            broker_order_id=broker_order_id,
            submitted_at=attempt.submitted_at,
            responded_at=responded_at,
            reason=reason or attempt.reason,
        )

    def has_event(self, order_id: UUID, event_identity: str) -> bool:
        return event_identity in self.events

    def get_event_hash(self, order_id: UUID, event_identity: str) -> str | None:
        return self.events.get(event_identity)

    def save_event(
        self,
        order_id: UUID,
        event: BrokerOrderEvent,
        new_state: OrderExecutionState,
        event_identity: str,
    ) -> None:
        if event_identity in self.events:
            raise RuntimeError("duplicate event (unique constraint)")
        self.events[event_identity] = event_content_hash(event)
        self.order_states[order_id] = new_state
        self.saved_events.append((order_id, event))

    def load_execution_state(self, order_id: UUID) -> OrderExecutionState | None:
        return self.order_states.get(order_id)


def _split_attempt_id(attempt_id: str) -> tuple[str, int]:
    execution_id, number = attempt_id.rsplit("-a", 1)
    return execution_id, int(number)


def make_event(
    order_id: UUID,
    event_type: OrderEventType,
    *,
    fill_quantity: Decimal = Decimal("0"),
    broker_order_id: str = "broker-1",
    source_event_id: str | None = None,
    reason: str = "test event",
) -> BrokerOrderEvent:
    metadata = {}
    if source_event_id is not None:
        metadata["source_event_id"] = source_event_id
    return BrokerOrderEvent(
        order_id=order_id,
        event_type=event_type,
        occurred_at=datetime.now(UTC),
        reason=reason,
        broker_order_id=broker_order_id,
        fill_quantity=fill_quantity,
        metadata=metadata,
    )
