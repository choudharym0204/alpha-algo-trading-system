"""Transactional order + event persistence (Phase 8).

COMMIT is the boundary of truth. Order creation persists the order and its
initial lifecycle event in a single transaction; any failure rolls back with no
false success. Idempotency is back-stopped by the ``orchestration_id`` and
``order_identity_key`` unique constraints (the in-memory find-first is only an
optimization). Events are append-oriented and never rewritten.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from alpha_algo_shared.db.models.safety import OrderEvent
from alpha_algo_shared.db.models.trading import Order

from alpha_algo_oms.identity import OrderIdentity
from alpha_algo_oms.validation import OrderSpec

OUTCOME_CREATED = "created"
OUTCOME_DUPLICATE = "duplicate"


def to_orm_order(spec: OrderSpec, identity: OrderIdentity) -> Order:
    """Build an ``Order`` ORM row from a validated spec + identity.

    The broker order id is intentionally left ``None`` (execution placeholder;
    Phase 9 assigns it). The initial lifecycle status is ``INTENT_CREATED``.
    """
    return Order(
        id=identity.internal_order_id,
        orchestration_id=spec.orchestration_id,
        order_identity_key=identity.order_identity_key,
        correlation_id=identity.correlation_id,
        strategy_id=spec.strategy_id,
        strategy_version=spec.strategy_version,
        strategy_run_id=spec.strategy_run_id,
        risk_approval_id=spec.risk_approval_id,
        approval_expires_at=spec.approval_expires_at,
        signal_id=spec.signal_id,
        instrument_id=spec.instrument_id,
        broker_account_id=spec.account_id,
        trading_mode=spec.trading_mode,
        client_order_id=identity.client_order_id,
        broker_order_id=None,
        side=spec.side,
        order_type=spec.order_type,
        quantity=spec.quantity,
        limit_price=spec.limit_price,
        stop_price=None,
        status="INTENT_CREATED",
    )


def to_orm_event(
    *,
    order_id: UUID,
    event_type: str,
    previous_status: str | None,
    new_status: str,
    event_timestamp,
    reason: str,
    source_event_id: str | None = None,
    broker_order_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> OrderEvent:
    return OrderEvent(
        order_id=order_id,
        source_event_id=source_event_id,
        event_type=event_type,
        previous_status=previous_status,
        new_status=new_status,
        broker_order_id=broker_order_id,
        event_timestamp=event_timestamp,
        reason=reason,
        event_payload=payload or {},
    )


class OrderRepository:
    """Persists ``Order`` and ``OrderEvent`` rows. COMMIT = truth."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def find_by_orchestration_id(self, orchestration_id: str) -> Order | None:
        session = self._session_factory()
        try:
            return session.execute(
                select(Order).where(Order.orchestration_id == orchestration_id)
            ).scalar_one_or_none()
        finally:
            session.close()

    def find_by_id(self, order_id: UUID) -> Order | None:
        session = self._session_factory()
        try:
            return session.get(Order, order_id)
        finally:
            session.close()

    def find_by_client_order_id(self, client_order_id: str) -> Order | None:
        session = self._session_factory()
        try:
            return session.execute(
                select(Order).where(Order.client_order_id == client_order_id)
            ).scalar_one_or_none()
        finally:
            session.close()

    def list_orders(self, *, limit: int = 100) -> list[Order]:
        session = self._session_factory()
        try:
            return list(
                session.execute(select(Order).limit(limit)).scalars().all()
            )
        finally:
            session.close()

    def get_events(self, order_id: UUID) -> list[OrderEvent]:
        session = self._session_factory()
        try:
            return list(
                session.execute(
                    select(OrderEvent)
                    .where(OrderEvent.order_id == order_id)
                    .order_by(OrderEvent.event_timestamp)
                ).scalars().all()
            )
        finally:
            session.close()

    def create_order(
        self, order: Order, initial_event: OrderEvent
    ) -> tuple[str, UUID]:
        """Persist a new order + its initial event in one transaction.

        A unique-constraint violation (concurrent duplicate insert) is converted
        to ``OUTCOME_DUPLICATE`` by re-reading the winning row — the durable
        backstop for exactly-one-order semantics.
        """
        session = self._session_factory()
        try:
            existing = session.execute(
                select(Order.id).where(
                    Order.orchestration_id == order.orchestration_id
                )
            ).scalar_one_or_none()
            if existing is not None:
                return OUTCOME_DUPLICATE, existing

            session.add(order)
            initial_event.order_id = order.id
            session.add(initial_event)
            session.commit()
            return OUTCOME_CREATED, order.id
        except IntegrityError:
            session.rollback()
            existing = session.execute(
                select(Order.id).where(
                    Order.orchestration_id == order.orchestration_id
                )
            ).scalar_one_or_none()
            return OUTCOME_DUPLICATE, existing
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def append_event(
        self, order_id: UUID, event: OrderEvent, *, new_status: str
    ) -> None:
        """Append an order lifecycle event and update the order status.

        Appends the event (append-only) and sets the order's current status in a
        single transaction. Never rewrites historical events.
        """
        session = self._session_factory()
        try:
            order = session.get(Order, order_id)
            if order is None:
                raise KeyError(f"order not found: {order_id}")
            order.status = new_status
            event.order_id = order_id
            session.add(event)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
