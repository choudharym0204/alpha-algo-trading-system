from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from alpha_algo_execution_engine.lifecycle import (
    InvalidOrderTransition,
    OrderLifecycle,
    OrderState,
)


class OrderEventType(StrEnum):
    BROKER_ACKNOWLEDGED = "BROKER_ACKNOWLEDGED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILL = "FILL"
    REJECTED = "REJECTED"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class InvalidOrderEvent(ValueError):
    pass


def _require_timezone(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class BrokerOrderEvent:
    order_id: UUID
    event_type: OrderEventType
    occurred_at: datetime
    reason: str
    broker_order_id: str | None = None
    fill_quantity: Decimal = Decimal("0")
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_timezone(self.occurred_at, "occurred_at")
        if not self.reason.strip():
            raise ValueError("reason is required")
        if self.fill_quantity < Decimal("0"):
            raise ValueError("fill_quantity cannot be negative")
        if self.event_type in {OrderEventType.PARTIAL_FILL, OrderEventType.FILL}:
            if self.fill_quantity <= Decimal("0"):
                raise ValueError("fill events require positive fill_quantity")
        elif self.fill_quantity != Decimal("0"):
            raise ValueError("non-fill events cannot carry fill_quantity")


@dataclass(frozen=True)
class OrderExecutionState:
    lifecycle: OrderLifecycle
    order_quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    broker_order_id: str | None = None

    def __post_init__(self) -> None:
        if self.order_quantity <= Decimal("0"):
            raise ValueError("order_quantity must be positive")
        if self.filled_quantity < Decimal("0"):
            raise ValueError("filled_quantity cannot be negative")
        if self.filled_quantity > self.order_quantity:
            raise ValueError("filled_quantity cannot exceed order_quantity")

    def apply_event(self, event: BrokerOrderEvent) -> OrderExecutionState:
        if event.order_id != self.lifecycle.order_id:
            raise InvalidOrderEvent("event order_id does not match lifecycle")

        if event.event_type == OrderEventType.BROKER_ACKNOWLEDGED:
            return self._with_transition(event, OrderState.BROKER_ACKNOWLEDGED)
        if event.event_type == OrderEventType.PARTIAL_FILL:
            return self._apply_partial_fill(event)
        if event.event_type == OrderEventType.FILL:
            return self._apply_fill(event)
        if event.event_type == OrderEventType.REJECTED:
            return self._with_transition(event, OrderState.REJECTED)
        if event.event_type == OrderEventType.CANCEL_REQUESTED:
            return self._with_transition(event, OrderState.CANCEL_REQUESTED)
        if event.event_type == OrderEventType.CANCELLED:
            return self._with_transition(event, OrderState.CANCELLED)
        if event.event_type == OrderEventType.UNKNOWN:
            return self._with_transition(event, OrderState.UNKNOWN)
        if event.event_type == OrderEventType.RECONCILIATION_REQUIRED:
            return self._with_transition(event, OrderState.RECONCILIATION_REQUIRED)
        raise InvalidOrderEvent(f"unsupported order event type: {event.event_type}")

    def _apply_partial_fill(self, event: BrokerOrderEvent) -> OrderExecutionState:
        next_filled_quantity = self.filled_quantity + event.fill_quantity
        if next_filled_quantity >= self.order_quantity:
            raise InvalidOrderEvent("partial fill cannot complete or overfill the order")
        return self._with_transition(
            event,
            OrderState.PARTIALLY_FILLED,
            filled_quantity=next_filled_quantity,
        )

    def _apply_fill(self, event: BrokerOrderEvent) -> OrderExecutionState:
        next_filled_quantity = self.filled_quantity + event.fill_quantity
        if next_filled_quantity != self.order_quantity:
            raise InvalidOrderEvent("fill event must complete the order quantity exactly")
        return self._with_transition(
            event,
            OrderState.FILLED,
            filled_quantity=next_filled_quantity,
        )

    def _with_transition(
        self,
        event: BrokerOrderEvent,
        to_state: OrderState,
        *,
        filled_quantity: Decimal | None = None,
    ) -> OrderExecutionState:
        try:
            next_lifecycle = self.lifecycle.transition_to(
                to_state,
                occurred_at=event.occurred_at,
                reason=event.reason,
                metadata={
                    "broker_order_id": event.broker_order_id,
                    "event_type": event.event_type,
                    **event.metadata,
                },
            )
        except InvalidOrderTransition:
            raise

        return OrderExecutionState(
            lifecycle=next_lifecycle,
            order_quantity=self.order_quantity,
            filled_quantity=self.filled_quantity
            if filled_quantity is None
            else filled_quantity,
            broker_order_id=event.broker_order_id or self.broker_order_id,
        )
