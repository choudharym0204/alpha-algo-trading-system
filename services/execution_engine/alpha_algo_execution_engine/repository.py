"""SQLAlchemy execution repository (Phase 9).

Durable persistence for execution attempts (`execution_attempts`), order events
(`order_events`), and order execution state (`orders`). COMMIT is the boundary
of truth; every event is append-only and keyed on a stable `event_identity`
stored in `OrderEvent.source_event_id` for idempotency.

NOTE: live PostgreSQL verification is deferred (no Docker in this environment);
this repository is exercised through the in-memory test double, with the
model/migration verified by schema tests.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from alpha_algo_execution_engine.events import (
    BrokerOrderEvent,
    OrderEventType,
    OrderExecutionState,
)
from alpha_algo_execution_engine.identity import event_content_hash
from alpha_algo_execution_engine.lifecycle import OrderLifecycle, OrderState
from alpha_algo_execution_engine.state import (
    ExecutionAttempt,
    ExecutionSubmissionState,
)
from alpha_algo_shared.db.models.execution import ExecutionAttemptRecord
from alpha_algo_shared.db.models.safety import OrderEvent
from alpha_algo_shared.db.models.trading import Order


def to_orm_attempt(attempt: ExecutionAttempt) -> ExecutionAttemptRecord:
    return ExecutionAttemptRecord(
        execution_id=attempt.execution_id,
        attempt_number=attempt.attempt_number,
        order_id=attempt.order_id,
        state=attempt.state.value,
        broker_order_id=attempt.broker_order_id,
        submitted_at=attempt.submitted_at,
        responded_at=attempt.responded_at,
        reason=attempt.reason,
    )


def from_orm_attempt(rec: ExecutionAttemptRecord) -> ExecutionAttempt:
    from alpha_algo_execution_engine.identity import compute_attempt_id

    return ExecutionAttempt(
        attempt_id=compute_attempt_id(rec.execution_id, rec.attempt_number),
        execution_id=rec.execution_id,
        order_id=rec.order_id,
        attempt_number=rec.attempt_number,
        state=ExecutionSubmissionState(rec.state),
        broker_order_id=rec.broker_order_id,
        submitted_at=rec.submitted_at,
        responded_at=rec.responded_at,
        reason=rec.reason or "",
    )


class ExecutionRepository:
    """SQLAlchemy-backed execution state store (implements the engine protocol)."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    # ----------------------------------------------------------------- attempts
    def find_attempt(
        self, execution_id: str, attempt_number: int
    ) -> ExecutionAttempt | None:
        session = self._session_factory()
        try:
            rec = session.execute(
                select(ExecutionAttemptRecord).where(
                    ExecutionAttemptRecord.execution_id == execution_id,
                    ExecutionAttemptRecord.attempt_number == attempt_number,
                )
            ).scalar_one_or_none()
            return from_orm_attempt(rec) if rec is not None else None
        finally:
            session.close()

    def save_attempt(self, attempt: ExecutionAttempt) -> None:
        session = self._session_factory()
        try:
            session.add(to_orm_attempt(attempt))
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_attempt(
        self,
        attempt_id: str,
        *,
        state: ExecutionSubmissionState,
        broker_order_id: str | None = None,
        responded_at: datetime | None = None,
        reason: str | None = None,
    ) -> None:
        session = self._session_factory()
        try:
            rec = session.execute(
                select(ExecutionAttemptRecord).where(
                    ExecutionAttemptRecord.execution_id
                    == _execution_id_from_attempt_id(attempt_id)
                )
            ).scalar_one_or_none()
            if rec is not None:
                rec.state = state.value
                if broker_order_id is not None:
                    rec.broker_order_id = broker_order_id
                if responded_at is not None:
                    rec.responded_at = responded_at
                if reason is not None:
                    rec.reason = reason
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------ events
    def has_event(self, order_id: UUID, event_identity: str) -> bool:
        session = self._session_factory()
        try:
            existing = session.execute(
                select(OrderEvent.id).where(
                    OrderEvent.source_event_id == event_identity
                )
            ).scalar_one_or_none()
            return existing is not None
        finally:
            session.close()

    def get_event_hash(self, order_id: UUID, event_identity: str) -> str | None:
        session = self._session_factory()
        try:
            rec = session.execute(
                select(OrderEvent).where(
                    OrderEvent.source_event_id == event_identity
                )
            ).scalar_one_or_none()
            if rec is None or rec.event_payload is None:
                return None
            return rec.event_payload.get("_content_hash")
        finally:
            session.close()

    def save_event(
        self,
        order_id: UUID,
        event: BrokerOrderEvent,
        new_state: OrderExecutionState,
        event_identity: str,
    ) -> None:
        session = self._session_factory()
        try:
            order = session.get(Order, order_id)
            if order is None:
                raise KeyError(f"order not found: {order_id}")
            order.status = new_state.lifecycle.state.value
            order.filled_quantity = int(new_state.filled_quantity)
            if new_state.broker_order_id is not None:
                order.broker_order_id = new_state.broker_order_id
            self._apply_event_timestamp(order, event)

            session.add(
                OrderEvent(
                    order_id=order_id,
                    source_event_id=event_identity,
                    event_type=event.event_type.value,
                    previous_status=event.event_type.value,
                    new_status=new_state.lifecycle.state.value,
                    broker_order_id=event.broker_order_id,
                    event_timestamp=event.occurred_at,
                    reason=event.reason,
                    event_payload={**(event.metadata or {}), "_content_hash": event_content_hash(event)},
                )
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def load_execution_state(self, order_id: UUID) -> OrderExecutionState | None:
        session = self._session_factory()
        try:
            order = session.get(Order, order_id)
            if order is None:
                return None
            lifecycle = OrderLifecycle(
                order_id=order.id, state=OrderState(order.status)
            )
            return OrderExecutionState(
                lifecycle=lifecycle,
                order_quantity=Decimal(order.quantity),
                filled_quantity=Decimal(order.filled_quantity or 0),
                broker_order_id=order.broker_order_id,
            )
        finally:
            session.close()

    @staticmethod
    def _apply_event_timestamp(order: Order, event: BrokerOrderEvent) -> None:
        if event.event_type == OrderEventType.BROKER_ACKNOWLEDGED:
            order.acknowledged_at = event.occurred_at
        elif event.event_type == OrderEventType.FILL:
            order.filled_at = event.occurred_at
        elif event.event_type == OrderEventType.REJECTED:
            order.rejected_at = event.occurred_at
        elif event.event_type == OrderEventType.CANCELLED:
            order.canceled_at = event.occurred_at


def _execution_id_from_attempt_id(attempt_id: str) -> str:
    """attempt_id is `<execution_id>-a<number>`; recover the execution_id."""
    return attempt_id.rsplit("-a", 1)[0]
